"""A Python class hierarchy wrapping a git repository and its
contents."""

import os, os.path, re
from datetime import datetime, timedelta, tzinfo

from stgit import exception, run, utils
from stgit.config import config

class Immutable(object):
    """I{Immutable} objects cannot be modified once created. Any
    modification methods will return a new object, leaving the
    original object as it was.

    The reason for this is that we want to be able to represent git
    objects, which are immutable, and want to be able to create new
    git objects that are just slight modifications of other git
    objects. (Such as, for example, modifying the commit message of a
    commit object while leaving the rest of it intact. This involves
    creating a whole new commit object that's exactly like the old one
    except for the commit message.)

    The L{Immutable} class doesn't acytually enforce immutability --
    that is up to the individual immutable subclasses. It just serves
    as documentation."""

class RepositoryException(exception.StgException):
    """Base class for all exceptions due to failed L{Repository}
    operations."""

class DateException(exception.StgException):
    """Exception raised when a date+time string could not be parsed."""
    def __init__(self, string, type):
        exception.StgException.__init__(
            self, '"%s" is not a valid %s' % (string, type))

class DetachedHeadException(RepositoryException):
    """Exception raised when HEAD is detached (that is, there is no
    current branch)."""
    def __init__(self):
        RepositoryException.__init__(self, 'Not on any branch')

class Repr(object):
    """Utility class that defines C{__reps__} in terms of C{__str__}."""
    def __repr__(self):
        return str(self)

class NoValue(object):
    """A handy default value that is guaranteed to be distinct from any
    real argument value."""
    pass

def make_defaults(defaults):
    def d(val, attr, default_fun = lambda: None):
        if val != NoValue:
            return val
        elif defaults != NoValue:
            return getattr(defaults, attr)
        else:
            return default_fun()
    return d

class TimeZone(tzinfo, Repr):
    """A simple time zone class for static offsets from UTC. (We have to
    define our own since Python's standard library doesn't define any
    time zone classes.)"""
    def __init__(self, tzstring):
        m = re.match(r'^([+-])(\d{2}):?(\d{2})$', tzstring)
        if not m:
            raise DateException(tzstring, 'time zone')
        sign = int(m.group(1) + '1')
        try:
            self.__offset = timedelta(hours = sign*int(m.group(2)),
                                      minutes = sign*int(m.group(3)))
        except OverflowError:
            raise DateException(tzstring, 'time zone')
        self.__name = tzstring
    def utcoffset(self, dt):
        return self.__offset
    def tzname(self, dt):
        return self.__name
    def dst(self, dt):
        return timedelta(0)
    def __str__(self):
        return self.__name

class Date(Immutable, Repr):
    """Represents a timestamp used in git commits."""
    def __init__(self, datestring):
        # Try git-formatted date.
        m = re.match(r'^(\d+)\s+([+-]\d\d:?\d\d)$', datestring)
        if m:
            try:
                self.__time = datetime.fromtimestamp(int(m.group(1)),
                                                     TimeZone(m.group(2)))
            except ValueError:
                raise DateException(datestring, 'date')
            return

        # Try iso-formatted date.
        m = re.match(r'^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s+'
                     + r'([+-]\d\d:?\d\d)$', datestring)
        if m:
            try:
                self.__time = datetime(
                    *[int(m.group(i + 1)) for i in xrange(6)],
                    **{'tzinfo': TimeZone(m.group(7))})
            except ValueError:
                raise DateException(datestring, 'date')
            return

        raise DateException(datestring, 'date')
    def __str__(self):
        return self.isoformat()
    def isoformat(self):
        """Human-friendly ISO 8601 format."""
        return '%s %s' % (self.__time.replace(tzinfo = None).isoformat(' '),
                          self.__time.tzinfo)
    @classmethod
    def maybe(cls, datestring):
        """Return a new object initialized with the argument if it contains a
        value (otherwise, just return the argument)."""
        if datestring in [None, NoValue]:
            return datestring
        return cls(datestring)

class Person(Immutable, Repr):
    """Represents an author or committer in a git commit object. Contains
    name, email and timestamp."""
    def __init__(self, name = NoValue, email = NoValue,
                 date = NoValue, defaults = NoValue):
        d = make_defaults(defaults)
        self.__name = d(name, 'name')
        self.__email = d(email, 'email')
        self.__date = d(date, 'date')
        assert isinstance(self.__date, Date) or self.__date in [None, NoValue]
    name = property(lambda self: self.__name)
    email = property(lambda self: self.__email)
    date = property(lambda self: self.__date)
    def set_name(self, name):
        return type(self)(name = name, defaults = self)
    def set_email(self, email):
        return type(self)(email = email, defaults = self)
    def set_date(self, date):
        return type(self)(date = date, defaults = self)
    def __str__(self):
        return '%s <%s> %s' % (self.name, self.email, self.date)
    @classmethod
    def parse(cls, s):
        m = re.match(r'^([^<]*)<([^>]*)>\s+(\d+\s+[+-]\d{4})$', s)
        assert m
        name = m.group(1).strip()
        email = m.group(2)
        date = Date(m.group(3))
        return cls(name, email, date)
    @classmethod
    def user(cls):
        if not hasattr(cls, '__user'):
            cls.__user = cls(name = config.get('user.name'),
                             email = config.get('user.email'))
        return cls.__user
    @classmethod
    def author(cls):
        if not hasattr(cls, '__author'):
            cls.__author = cls(
                name = os.environ.get('GIT_AUTHOR_NAME', NoValue),
                email = os.environ.get('GIT_AUTHOR_EMAIL', NoValue),
                date = Date.maybe(os.environ.get('GIT_AUTHOR_DATE', NoValue)),
                defaults = cls.user())
        return cls.__author
    @classmethod
    def committer(cls):
        if not hasattr(cls, '__committer'):
            cls.__committer = cls(
                name = os.environ.get('GIT_COMMITTER_NAME', NoValue),
                email = os.environ.get('GIT_COMMITTER_EMAIL', NoValue),
                date = Date.maybe(
                    os.environ.get('GIT_COMMITTER_DATE', NoValue)),
                defaults = cls.user())
        return cls.__committer

class Tree(Immutable, Repr):
    """Represents a git tree object."""
    def __init__(self, sha1):
        self.__sha1 = sha1
    sha1 = property(lambda self: self.__sha1)
    def __str__(self):
        return 'Tree<%s>' % self.sha1

class CommitData(Immutable, Repr):
    """Represents the actual data contents of a git commit object."""
    def __init__(self, tree = NoValue, parents = NoValue, author = NoValue,
                 committer = NoValue, message = NoValue, defaults = NoValue):
        d = make_defaults(defaults)
        self.__tree = d(tree, 'tree')
        self.__parents = d(parents, 'parents')
        self.__author = d(author, 'author', Person.author)
        self.__committer = d(committer, 'committer', Person.committer)
        self.__message = d(message, 'message')
    tree = property(lambda self: self.__tree)
    parents = property(lambda self: self.__parents)
    @property
    def parent(self):
        assert len(self.__parents) == 1
        return self.__parents[0]
    author = property(lambda self: self.__author)
    committer = property(lambda self: self.__committer)
    message = property(lambda self: self.__message)
    def set_tree(self, tree):
        return type(self)(tree = tree, defaults = self)
    def set_parents(self, parents):
        return type(self)(parents = parents, defaults = self)
    def add_parent(self, parent):
        return type(self)(parents = list(self.parents or []) + [parent],
                          defaults = self)
    def set_parent(self, parent):
        return self.set_parents([parent])
    def set_author(self, author):
        return type(self)(author = author, defaults = self)
    def set_committer(self, committer):
        return type(self)(committer = committer, defaults = self)
    def set_message(self, message):
        return type(self)(message = message, defaults = self)
    def is_nochange(self):
        return len(self.parents) == 1 and self.tree == self.parent.data.tree
    def __str__(self):
        if self.tree == None:
            tree = None
        else:
            tree = self.tree.sha1
        if self.parents == None:
            parents = None
        else:
            parents = [p.sha1 for p in self.parents]
        return ('CommitData<tree: %s, parents: %s, author: %s,'
                ' committer: %s, message: "%s">'
                ) % (tree, parents, self.author, self.committer, self.message)
    @classmethod
    def parse(cls, repository, s):
        cd = cls(parents = [])
        lines = list(s.splitlines(True))
        for i in xrange(len(lines)):
            line = lines[i].strip()
            if not line:
                return cd.set_message(''.join(lines[i+1:]))
            key, value = line.split(None, 1)
            if key == 'tree':
                cd = cd.set_tree(repository.get_tree(value))
            elif key == 'parent':
                cd = cd.add_parent(repository.get_commit(value))
            elif key == 'author':
                cd = cd.set_author(Person.parse(value))
            elif key == 'committer':
                cd = cd.set_committer(Person.parse(value))
            else:
                assert False
        assert False

class Commit(Immutable, Repr):
    """Represents a git commit object. All the actual data contents of the
    commit object is stored in the L{data} member, which is a
    L{CommitData} object."""
    def __init__(self, repository, sha1):
        self.__sha1 = sha1
        self.__repository = repository
        self.__data = None
    sha1 = property(lambda self: self.__sha1)
    @property
    def data(self):
        if self.__data == None:
            self.__data = CommitData.parse(
                self.__repository,
                self.__repository.cat_object(self.sha1))
        return self.__data
    def __str__(self):
        return 'Commit<sha1: %s, data: %s>' % (self.sha1, self.__data)

class Refs(object):
    """Accessor for the refs stored in a git repository. Will
    transparently cache the values of all refs."""
    def __init__(self, repository):
        self.__repository = repository
        self.__refs = None
    def __cache_refs(self):
        """(Re-)Build the cache of all refs in the repository."""
        self.__refs = {}
        for line in self.__repository.run(['git', 'show-ref']).output_lines():
            m = re.match(r'^([0-9a-f]{40})\s+(\S+)$', line)
            sha1, ref = m.groups()
            self.__refs[ref] = sha1
    def get(self, ref):
        """Get the Commit the given ref points to. Throws KeyError if ref
        doesn't exist."""
        if self.__refs == None:
            self.__cache_refs()
        return self.__repository.get_commit(self.__refs[ref])
    def exists(self, ref):
        """Check if the given ref exists."""
        try:
            self.get(ref)
        except KeyError:
            return False
        else:
            return True
    def set(self, ref, commit, msg):
        """Write the sha1 of the given Commit to the ref. The ref may or may
        not already exist."""
        if self.__refs == None:
            self.__cache_refs()
        old_sha1 = self.__refs.get(ref, '0'*40)
        new_sha1 = commit.sha1
        if old_sha1 != new_sha1:
            self.__repository.run(['git', 'update-ref', '-m', msg,
                                   ref, new_sha1, old_sha1]).no_output()
            self.__refs[ref] = new_sha1
    def delete(self, ref):
        """Delete the given ref. Throws KeyError if ref doesn't exist."""
        if self.__refs == None:
            self.__cache_refs()
        self.__repository.run(['git', 'update-ref',
                               '-d', ref, self.__refs[ref]]).no_output()
        del self.__refs[ref]

class ObjectCache(object):
    """Cache for Python objects, for making sure that we create only one
    Python object per git object. This reduces memory consumption and
    makes object comparison very cheap."""
    def __init__(self, create):
        self.__objects = {}
        self.__create = create
    def __getitem__(self, name):
        if not name in self.__objects:
            self.__objects[name] = self.__create(name)
        return self.__objects[name]
    def __contains__(self, name):
        return name in self.__objects
    def __setitem__(self, name, val):
        assert not name in self.__objects
        self.__objects[name] = val

class RunWithEnv(object):
    def run(self, args, env = {}):
        """Run the given command with an environment given by self.env.

        @type args: list of strings
        @param args: Command and argument vector
        @type env: dict
        @param env: Extra environment"""
        return run.Run(*args).env(utils.add_dict(self.env, env))

class RunWithEnvCwd(RunWithEnv):
    def run(self, args, env = {}):
        """Run the given command with an environment given by self.env, and
        current working directory given by self.cwd.

        @type args: list of strings
        @param args: Command and argument vector
        @type env: dict
        @param env: Extra environment"""
        return RunWithEnv.run(self, args, env).cwd(self.cwd)

class Repository(RunWithEnv):
    """Represents a git repository."""
    def __init__(self, directory):
        self.__git_dir = directory
        self.__refs = Refs(self)
        self.__trees = ObjectCache(lambda sha1: Tree(sha1))
        self.__commits = ObjectCache(lambda sha1: Commit(self, sha1))
        self.__default_index = None
        self.__default_worktree = None
        self.__default_iw = None
    env = property(lambda self: { 'GIT_DIR': self.__git_dir })
    @classmethod
    def default(cls):
        """Return the default repository."""
        try:
            return cls(run.Run('git', 'rev-parse', '--git-dir'
                               ).output_one_line())
        except run.RunException:
            raise RepositoryException('Cannot find git repository')
    @property
    def default_index(self):
        """An L{Index} object representing the default index file for the
        repository."""
        if self.__default_index == None:
            self.__default_index = Index(
                self, (os.environ.get('GIT_INDEX_FILE', None)
                       or os.path.join(self.__git_dir, 'index')))
        return self.__default_index
    def temp_index(self):
        """Return an L{Index} object representing a new temporary index file
        for the repository."""
        return Index(self, self.__git_dir)
    @property
    def default_worktree(self):
        """A L{Worktree} object representing the default work tree."""
        if self.__default_worktree == None:
            path = os.environ.get('GIT_WORK_TREE', None)
            if not path:
                o = run.Run('git', 'rev-parse', '--show-cdup').output_lines()
                o = o or ['.']
                assert len(o) == 1
                path = o[0]
            self.__default_worktree = Worktree(path)
        return self.__default_worktree
    @property
    def default_iw(self):
        """An L{IndexAndWorktree} object representing the default index and
        work tree for this repository."""
        if self.__default_iw == None:
            self.__default_iw = IndexAndWorktree(self.default_index,
                                                 self.default_worktree)
        return self.__default_iw
    directory = property(lambda self: self.__git_dir)
    refs = property(lambda self: self.__refs)
    def cat_object(self, sha1):
        return self.run(['git', 'cat-file', '-p', sha1]).raw_output()
    def rev_parse(self, rev):
        try:
            return self.get_commit(self.run(
                    ['git', 'rev-parse', '%s^{commit}' % rev]
                    ).output_one_line())
        except run.RunException:
            raise RepositoryException('%s: No such revision' % rev)
    def get_tree(self, sha1):
        return self.__trees[sha1]
    def get_commit(self, sha1):
        return self.__commits[sha1]
    def commit(self, commitdata):
        c = ['git', 'commit-tree', commitdata.tree.sha1]
        for p in commitdata.parents:
            c.append('-p')
            c.append(p.sha1)
        env = {}
        for p, v1 in ((commitdata.author, 'AUTHOR'),
                       (commitdata.committer, 'COMMITTER')):
            if p != None:
                for attr, v2 in (('name', 'NAME'), ('email', 'EMAIL'),
                                 ('date', 'DATE')):
                    if getattr(p, attr) != None:
                        env['GIT_%s_%s' % (v1, v2)] = str(getattr(p, attr))
        sha1 = self.run(c, env = env).raw_input(commitdata.message
                                                ).output_one_line()
        return self.get_commit(sha1)
    @property
    def head(self):
        try:
            return self.run(['git', 'symbolic-ref', '-q', 'HEAD']
                            ).output_one_line()
        except run.RunException:
            raise DetachedHeadException()
    def set_head(self, ref, msg):
        self.run(['git', 'symbolic-ref', '-m', msg, 'HEAD', ref]).no_output()
    def simple_merge(self, base, ours, theirs):
        """Given three L{Tree}s, tries to do an in-index merge with a
        temporary index. Returns the result L{Tree}, or None if the
        merge failed (due to conflicts)."""
        assert isinstance(base, Tree)
        assert isinstance(ours, Tree)
        assert isinstance(theirs, Tree)

        # Take care of the really trivial cases.
        if base == ours:
            return theirs
        if base == theirs:
            return ours
        if ours == theirs:
            return ours

        index = self.temp_index()
        try:
            index.merge(base, ours, theirs)
            try:
                return index.write_tree()
            except MergeException:
                return None
        finally:
            index.delete()
    def apply(self, tree, patch_text):
        """Given a L{Tree} and a patch, will either return the new L{Tree}
        that results when the patch is applied, or None if the patch
        couldn't be applied."""
        assert isinstance(tree, Tree)
        if not patch_text:
            return tree
        index = self.temp_index()
        try:
            index.read_tree(tree)
            try:
                index.apply(patch_text)
                return index.write_tree()
            except MergeException:
                return None
        finally:
            index.delete()
    def diff_tree(self, t1, t2, diff_opts):
        """Given two L{Tree}s C{t1} and C{t2}, return the patch that takes
        C{t1} to C{t2}.

        @type diff_opts: list of strings
        @param diff_opts: Extra diff options
        @rtype: String
        @return: Patch text"""
        assert isinstance(t1, Tree)
        assert isinstance(t2, Tree)
        return self.run(['git', 'diff-tree', '-p'] + list(diff_opts)
                        + [t1.sha1, t2.sha1]).raw_output()

class MergeException(exception.StgException):
    """Exception raised when a merge fails for some reason."""

class MergeConflictException(MergeException):
    """Exception raised when a merge fails due to conflicts."""

class Index(RunWithEnv):
    """Represents a git index file."""
    def __init__(self, repository, filename):
        self.__repository = repository
        if os.path.isdir(filename):
            # Create a temp index in the given directory.
            self.__filename = os.path.join(
                filename, 'index.temp-%d-%x' % (os.getpid(), id(self)))
            self.delete()
        else:
            self.__filename = filename
    env = property(lambda self: utils.add_dict(
            self.__repository.env, { 'GIT_INDEX_FILE': self.__filename }))
    def read_tree(self, tree):
        self.run(['git', 'read-tree', tree.sha1]).no_output()
    def write_tree(self):
        try:
            return self.__repository.get_tree(
                self.run(['git', 'write-tree']).discard_stderr(
                    ).output_one_line())
        except run.RunException:
            raise MergeException('Conflicting merge')
    def is_clean(self):
        try:
            self.run(['git', 'update-index', '--refresh']).discard_output()
        except run.RunException:
            return False
        else:
            return True
    def merge(self, base, ours, theirs):
        """In-index merge, no worktree involved."""
        self.run(['git', 'read-tree', '-m', '-i', '--aggressive',
                  base.sha1, ours.sha1, theirs.sha1]).no_output()
    def apply(self, patch_text):
        """In-index patch application, no worktree involved."""
        try:
            self.run(['git', 'apply', '--cached']
                     ).raw_input(patch_text).no_output()
        except run.RunException:
            raise MergeException('Patch does not apply cleanly')
    def delete(self):
        if os.path.isfile(self.__filename):
            os.remove(self.__filename)
    def conflicts(self):
        """The set of conflicting paths."""
        paths = set()
        for line in self.run(['git', 'ls-files', '-z', '--unmerged']
                             ).raw_output().split('\0')[:-1]:
            stat, path = line.split('\t', 1)
            paths.add(path)
        return paths

class Worktree(object):
    """Represents a git worktree (that is, a checked-out file tree)."""
    def __init__(self, directory):
        self.__directory = directory
    env = property(lambda self: { 'GIT_WORK_TREE': '.' })
    directory = property(lambda self: self.__directory)

class CheckoutException(exception.StgException):
    """Exception raised when a checkout fails."""

class IndexAndWorktree(RunWithEnvCwd):
    """Represents a git index and a worktree. Anything that an index or
    worktree can do on their own are handled by the L{Index} and
    L{Worktree} classes; this class concerns itself with the
    operations that require both."""
    def __init__(self, index, worktree):
        self.__index = index
        self.__worktree = worktree
    index = property(lambda self: self.__index)
    env = property(lambda self: utils.add_dict(self.__index.env,
                                               self.__worktree.env))
    cwd = property(lambda self: self.__worktree.directory)
    def checkout(self, old_tree, new_tree):
        # TODO: Optionally do a 3-way instead of doing nothing when we
        # have a problem. Or maybe we should stash changes in a patch?
        assert isinstance(old_tree, Tree)
        assert isinstance(new_tree, Tree)
        try:
            self.run(['git', 'read-tree', '-u', '-m',
                      '--exclude-per-directory=.gitignore',
                      old_tree.sha1, new_tree.sha1]
                     ).discard_output()
        except run.RunException:
            raise CheckoutException('Index/workdir dirty')
    def merge(self, base, ours, theirs):
        assert isinstance(base, Tree)
        assert isinstance(ours, Tree)
        assert isinstance(theirs, Tree)
        try:
            r = self.run(['git', 'merge-recursive', base.sha1, '--', ours.sha1,
                          theirs.sha1],
                         env = { 'GITHEAD_%s' % base.sha1: 'ancestor',
                                 'GITHEAD_%s' % ours.sha1: 'current',
                                 'GITHEAD_%s' % theirs.sha1: 'patched'})
            r.discard_output()
        except run.RunException, e:
            if r.exitcode == 1:
                raise MergeConflictException()
            else:
                raise MergeException('Index/worktree dirty')
    def changed_files(self):
        return self.run(['git', 'diff-files', '--name-only']).output_lines()
    def update_index(self, files):
        self.run(['git', 'update-index', '--remove', '-z', '--stdin']
                 ).input_nulterm(files).discard_output()