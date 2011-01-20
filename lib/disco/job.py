"""
:mod:`disco.core` --- Disco Jobs
================================

.. autoclass:: JobDict
        :members: pack, unpack
.. autoclass:: Job
        :members:
.. autoclass:: Params
        :members:
"""
import sys

from disco import dencode, func, json, util
from disco.modutil import find_modules
from disco.settings import DiscoSettings
from disco.worker.classic import worker

class Params(object):
    """
    Parameter container for map / reduce tasks.

    This object provides a convenient way to contain custom parameters,
    or state, in your tasks.

    This example shows a simple way of using :class:`Params`::

        def fun_map(e, params):
                params.c += 1
                if not params.c % 10:
                        return [(params.f(e), params.c)]
                return [(e, params.c)]

        disco.new_job(name="disco://localhost",
                      input=["disco://localhost/myjob/file1"],
                      map=fun_map,
                      params=disco.core.Params(c=0, f=lambda x: x + "!"))

    You can specify any number of key-value pairs to the :class:`Params`.
    The pairs will be available to task functions through the *params* argument.
    Each task receives its own copy of the initial params object.
    *key* must be a valid Python identifier.
    *value* can be any Python object.
    For instance, *value* can be an arbitrary :term:`pure function`,
    such as *params.f* in the previous example.
    """
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getstate__(self):
        return dict((k, util.pack(v))
            for k, v in self.__dict__.iteritems()
                if not k.startswith('_'))

    def __setstate__(self, state):
        for k, v in state.iteritems():
            self.__dict__[k] = util.unpack(v)

class JobDict(util.DefaultDict):
    """
    :meth:`Disco.new_job` and :meth:`Job.run`
    accept the same set of keyword arguments as specified below.

    .. note:: All arguments that are required are marked as such.
              All other arguments are optional.

    :type  input: **required**, list of inputs or list of list of inputs
    :param input: Each input must be specified in one of the following ways:

                   * ``http://www.example.com/data`` - any HTTP address
                   * ``disco://cnode03/bigtxt/file_name`` - Disco address. Refers to ``cnode03:/var/disco/bigtxt/file_name``. Currently this is an alias for ``http://cnode03:[DISCO_PORT]/bigtxt/file_name``.
                   * ``dir://cnode03/jobname/`` - Result directory. This format is used by Disco internally.
                   * ``/home/bob/bigfile.txt`` - a local file. Note that the file must either exist on all the nodes or you must make sure that the job is run only on the nodes where the file exists. Due to these restrictions, this form has only limited use.
                   * ``raw://some_string`` - pseudo-address; instead of fetching data from a remote source, use ``some_string`` in the address as data. Useful for specifying dummy inputs for generator maps.
                   * ``tag://tagname`` - a tag stored in :ref:`DDFS` (*Added in version 0.3*)

                  (*Added in version 0.3.2*)
                  Tags can be token protected. For the data in such
                  token-protected tags to be used as job inputs, the
                  tags should be resolved into the constituent urls or
                  replica sets (e.g. using util.urllist), and provided
                  as the value of the input parameter.

                  (*Added in version 0.2.2*):
                  An input entry can be a list of inputs:
                  This lets you specify redundant versions of an input file.
                  If a list of redundant inputs is specified,
                  the scheduler chooses the input that is located on the node
                  with the lowest load at the time of scheduling.
                  Redundant inputs are tried one by one until the task succeeds.
                  Redundant inputs require that the *map* function is specified.

    :type  map: :func:`disco.func.map`
    :param map: a :term:`pure function` that defines the map task.

    :type  map_init: :func:`disco.func.init`
    :param map_init: initialization function for the map task.
                     This function is called once before the task starts.

    :type  map_input_stream: list of :func:`disco.func.input_stream`
    :param map_input_stream: The given functions are chained together and the final resulting
                             :class:`disco.func.InputStream` object is used
                             to iterate over input entries.

                             (*Added in version 0.2.4*)

    :type  map_output_stream: list of :func:`disco.func.output_stream`
    :param map_output_stream: The given functions are chained together and the
                              :meth:`disco.func.OutputStream.add` method of the last
                              returned :class:`disco.func.OutputStream` object is used
                              to serialize key, value pairs output by the map.
                              (*Added in version 0.2.4*)

    :type  map_reader: ``None`` or :func:`disco.func.input_stream`
    :param map_reader: Convenience function to define the last :func:`disco.func.input_stream`
                       function in the *map_input_stream* chain.

                       Disco worker provides a convenience function
                       :func:`disco.func.re_reader` that can be used to create
                       a reader using regular expressions.

                       If you want to use outputs of an earlier job as inputs,
                       use :func:`disco.func.chain_reader` as the *map_reader*.

                       Default is ``None``.

                       (*Changed after version 0.3.1*)
                       The default map_reader became ``None``.
                       See the note in :func:`disco.func.map_line_reader`
                       for information on how this might affect older jobs.

    :type  reduce: :func:`disco.func.reduce`
    :param reduce: If no reduce function is specified, the job will quit after
                   the map phase has finished.

                   *Added in version 0.3.1*:
                   Reduce supports now an alternative signature,
                   :func:`disco.func.reduce2` which uses an iterator instead
                   of ``out.add()`` to output results.

                   *Changed in version 0.2*:
                   It is possible to define only *reduce* without *map*.
                   For more information, see the FAQ entry :ref:`reduceonly`.

    :type  reduce_init: :func:`disco.func.init`
    :param reduce_init: initialization function for the reduce task.
                        This function is called once before the task starts.

    :type  reduce_input_stream: list of :func:`disco.func.output_stream`
    :param reduce_input_stream: The given functions are chained together and the last
                              returned :class:`disco.func.InputStream` object is
                              given to *reduce* as its first argument.
                              (*Added in version 0.2.4*)

    :type  reduce_output_stream: list of :func:`disco.func.output_stream`
    :param reduce_output_stream: The given functions are chained together and the last
                              returned :class:`disco.func.OutputStream` object is
                              given to *reduce* as its second argument.
                              (*Added in version 0.2.4*)

    :type  reduce_reader: :func:`disco.func.input_stream`
    :param reduce_reader: Convenience function to define the last func:`disco.func.input_stream`
                          if *map* is specified.
                          If *map* is not specified,
                          you can read arbitrary inputs with this function,
                          similar to *map_reader*.
                          (*Added in version 0.2*)

                          Default is :func:`disco.func.chain_reader`.

    :type  combiner: :func:`disco.func.combiner`
    :param combiner: called after the partitioning function, for each partition.

    :type  partition: :func:`disco.func.partition`
    :param partition: decides how the map output is distributed to reduce.

                      Default is :func:`disco.func.default_partition`.

    :type  partitions: int or None
    :param partitions: number of partitions, if any.

                       Default is ``1``.

    :type  merge_partitions: bool
    :param merge_partitions: whether or not to merge partitioned inputs during reduce.

                             Default is ``False``.

    :type  scheduler: dict
    :param scheduler: options for the job scheduler.
                      The following keys are supported:

                       * *max_cores* - use this many cores at most
                                       (applies to both map and reduce).

                                       Default is ``2**31``.

                       * *force_local* - always run task on the node where
                                         input data is located;
                                         never use HTTP to access data remotely.

                       * *force_remote* - never run task on the node where input
                                          data is located;
                                          always use HTTP to access data remotely.

                      (*Added in version 0.2.4*)

    :type  sort: boolean
    :param sort: flag specifying whether the intermediate results,
                 that is, input to the reduce function, should be sorted.
                 Sorting is most useful in ensuring that the equal keys are
                 consequent in the input for the reduce function.

                 Other than ensuring that equal keys are grouped together,
                 sorting ensures that keys are returned in the ascending order.
                 No other assumptions should be made on the comparison function.

                 The external program ``sort`` is used to sort the input on disk.
                 In-memory sort can easily be performed by the tasks themselves.

                 Default is ``False``.

    :type  params: :class:`Params`
    :param params: object that is passed to worker tasks to store state
                   The object is serialized using the *pickle* module,
                   so it should be pickleable.

                   A convience class :class:`Params` is provided that
                   provides an easy way to encapsulate a set of parameters.
                   :class:`Params` allows including
                   :term:`pure functions <pure function>` in the parameters.

    :param ext_params: if either map or reduce function is an external program,
                       typically specified using :func:`disco.util.external`,
                       this object is used to deliver parameters to the program.

                       See :mod:`disco.worker.classic.external`.

    :type  required_files: list of paths or dict
    :param required_files: additional files that are required by the job.
                           Either a list of paths to files to include,
                           or a dictionary which contains items of the form
                           ``(filename, filecontents)``.

                           You can use this parameter to include custom modules
                           or shared libraries in the job.
                           (*Added in version 0.2.3*)

                           .. note::

                                All files will be saved in a flat directory
                                on the worker.
                                No subdirectories will be created.


                            .. note::

                                ``LD_LIBRARY_PATH`` is set so you can include
                                a shared library ``foo.so`` in *required_files*
                                and load it in the job directly as
                                ``ctypes.cdll.LoadLibrary("foo.so")``.
                                For an example, see :ref:`discoext`.

    :param required_modules: required modules to send to the worker
                             (*Changed in version 0.2.3*):
                             Disco tries to guess which modules are needed
                             by your job functions automatically.
                             It sends any local dependencies
                             (i.e. modules not included in the
                             Python standard library) to nodes by default.

                             If guessing fails, or you have other requirements,
                             see :mod:`disco.modutil` for options.


    :type  status_interval: integer
    :param status_interval: print "K items mapped / reduced"
                            for every Nth item.
                            Setting the value to 0 disables messages.

                            Increase this value, or set it to zero,
                            if you get "Message rate limit exceeded"
                            error due to system messages.
                            This might happen if your tasks are really fast.
                            Decrease the value if you want more messages or
                            you don't have that many data items.

                            Default is ``100000``.

    :type  profile: boolean
    :param profile: enable tasks profiling.
                    Retrieve profiling results with :meth:`Disco.profile_stats`.

                    Default is ``False``.
    """
    defaults = {'input': (),
                'jobhome': worker.jobhome,
                'worker': DiscoSettings()['DISCO_WORKER'],
                'map?': False,
                'reduce?': False,
                'map': None,
                'map_init': func.noop,
                'map_reader': None,
                'map_input_stream': (func.map_input_stream, ),
                'map_output_stream': (func.map_output_stream,
                                      func.disco_output_stream),
                'combiner': None,
                'partition': func.default_partition,
                'reduce': None,
                'reduce_init': func.noop,
                'reduce_reader': func.chain_reader,
                'reduce_input_stream': (func.reduce_input_stream, ),
                'reduce_output_stream': (func.reduce_output_stream,
                                         func.disco_output_stream),
                'ext_params': {},
                'merge_partitions': False,
                'nr_reduces': 0,
                'params': Params(),
                'partitions': 1,
                'prefix': '',
                'profile': False,
                'required_files': {},
                'required_modules': None,
                'scheduler': {'force_local': False,
                              'force_remote': False,
                              'max_cores': int(2**31),},
                'save': False,
                'sort': False,
                'status_interval': 100000,
                'owner': DiscoSettings()['DISCO_JOB_OWNER'],
                'version': '.'.join(str(s) for s in sys.version_info[:2]),
                }
    default_factory = defaults.__getitem__

    master_keys = set(['prefix',
                       'input',
                       'jobhome',
                       'worker',
                       'owner',
                       'nr_reduces',
                       'scheduler',
                       'map?',
                       'reduce?'])

    funcs = set(['map',
                 'map_init',
                 'map_reader',
                 'combiner',
                 'partition',
                 'reduce',
                 'reduce_init',
                 'reduce_reader',
                 'map_input_stream',
                 'map_output_stream',
                 'reduce_input_stream',
                 'reduce_output_stream'])

    def __init__(self, ddfs=None, **kwargs):
        super(JobDict, self).__init__(**kwargs)

        # -- required modules and files --
        if self['required_modules'] is None:
            funcs = util.flatten(util.iterify(self[f]) for f in self.funcs)
            self['required_modules'] = find_modules([f for f in funcs
                                                     if callable(f)])

        # -- input --
        self['input'] = [list(util.iterify(url))
                         for i in self['input']
                         for url in util.urllist(i, listdirs=bool(self['map']),
                                                 ddfs=ddfs)]

        # partitions must be an integer internally
        self['partitions'] = self['partitions'] or 0
        # set nr_reduces: ignored if there is not actually a reduce specified
        if self['map']:
            # partitioned map has N reduces; non-partitioned map has 1 reduce
            self['nr_reduces'] = self['partitions'] or 1
        elif self.input_is_partitioned:
            # Only reduce, with partitions: len(dir://) specifies nr_reduces
            self['nr_reduces'] = 1 + max(id for dir in self['input']
                                         for id, url in util.read_index(dir[0]))
        else:
            # Only reduce, without partitions can only have 1 reduce
            self['nr_reduces'] = 1

        # merge_partitions iff the inputs to reduce are partitioned
        if self['merge_partitions']:
            if self['partitions'] or self.input_is_partitioned:
                self['nr_reduces'] = 1
            else:
                raise DiscoError("Can't merge partitions without partitions")

        # -- scheduler --
        scheduler = self.defaults['scheduler'].copy()
        scheduler.update(self['scheduler'])
        if scheduler['max_cores'] < 1:
            raise DiscoError("max_cores must be >= 1")
        self['scheduler'] = scheduler

        # job flow
        self['map?'] = bool(self['map'])
        self['reduce?'] = bool(self['reduce'])

    def __contains__(self, key):
        return key in self.defaults

    def pack(self):
        """Pack up the :class:`JobDict` for sending over the wire."""
        jobpack = {}

        if self['required_files']:
            if not isinstance(self['required_files'], dict):
                self['required_files'] = util.pack_files(self['required_files'])
        else:
            self['required_files'] = {}
        self['required_files'].update(util.pack_files(
            o[1] for o in self['required_modules'] if util.iskv(o)))

        for key in self.defaults:
            if key not in self.master_keys:
                jobpack[key] = util.pack(self[key])
            else:
                jobpack[key] = self[key]
        return dencode.dumps(jobpack)

    @classmethod
    def unpack(cls, jobpack, lib=None, globals={'__builtins__': __builtins__}):
        """Unpack the previously packed :class:`JobDict`."""
        jobdict = cls.defaults.copy()
        jobdict.update(**dencode.loads(jobpack))

        for key in jobdict:
            if key not in cls.master_keys:
                jobdict[key] = util.unpack(jobdict[key], globals=globals)

        if lib:
            util.unpack_files(jobdict['required_files'], lib)

        return cls(**jobdict)

    @property
    def input_is_partitioned(self):
        if self['input']:
            return all(url.startswith('dir://')
                       for urls in self['input']
                       for url in urls)

class Job(object):
    """
    Creates a Disco job with the given name.

    Use :meth:`Job.run` to start the job.

    You need not instantiate this class directly.
    Instead, the :meth:`Disco.new_job` can be used to create and start a job.

    :param master: An instance of the :class:`Disco` class that identifies
                   the Disco master runs this job. This argument is required but
                   it is provided automatically when the job is started using
                   :meth:`Disco.new_job`.

    :param name: The job name.
                 When you create a handle for an existing job, the name is used as given.
                 When you create a new job, the name given is used by Disco as a
                 prefix to construct a unique name, which is then stored in the instance.

                 .. note::

                        Only characters in ``[a-zA-Z0-9_]`` are allowed in the job name.

    All methods in :class:`Disco` that are related to individual jobs, namely

        - :meth:`Disco.clean`
        - :meth:`Disco.events`
        - :meth:`Disco.kill`
        - :meth:`Disco.jobinfo`
        - :meth:`Disco.jobspec`
        - :meth:`Disco.oob_get`
        - :meth:`Disco.oob_list`
        - :meth:`Disco.profile_stats`
        - :meth:`Disco.purge`
        - :meth:`Disco.results`
        - :meth:`Disco.wait`

    are also accessible through the :class:`Job` object, so you can say
    `job.wait()` instead of `Disco.wait(job.name)`. However, the job methods
    in :class:`Disco` come in handy if you want to manipulate a job that is
    identified by a job name (:attr:`Job.name`) instead of a :class:`Job`
    object.

    If you have access only to results of a job, you can extract the job
    name from an address with the :func:`disco.util.jobname` function. A typical
    case is that you are done with results of a job and they are not needed
    anymore. You can delete the unneeded job files as follows::

        from disco.core import Job
        from disco.util import jobname

        Job(master, jobname(results[0])).purge()
    """
    proxy_functions = ('clean',
                       'events',
                       'kill',
                       'jobinfo',
                       'jobspec',
                       'oob_get',
                       'oob_list',
                       'profile_stats',
                       'purge',
                       'results',
                       'mapresults',
                       'wait')

    def __init__(self, master, name):
        self.master  = master
        self.name    = name

    def __getattr__(self, attr):
        if attr in self.proxy_functions:
            from functools import partial
            return partial(getattr(self.master, attr), self.name)
        raise AttributeError("%r has no attribute %r" % (self, attr))

    class JobDict(JobDict):
        def __init__(self, job, *args, **kwargs):
            self.job = job
            super(Job.JobDict, self).__init__(*args, **kwargs)

        def default_factory(self, attr):
            try:
                return getattr(self.job, attr)
            except AttributeError:
                return self.defaults.__getitem__(attr)

    def run(self, **kwargs):
        """
        Returns the job immediately after the request has been submitted.

        Accepts the same set of keyword arguments as :class:`JobDict`.

        A typical pattern in Disco scripts is to run a job synchronously,
        that is, to block the script until the job has finished.
        This is accomplished as follows::

                from disco.core import Disco
                results = Disco(master).new_job(...).wait()

        Note that job methods of the :class:`Disco` class are directly
        accessible through the :class:`Job` object, such as :meth:`Disco.wait`
        above.

        A :class:`JobError` is raised if an error occurs while starting the job.
        """
        jobpack = Job.JobDict(self,
                              prefix=self.name,
                              ddfs=self.master.master,
                              **kwargs).pack()
        status, response = json.loads(self.master.request('/disco/job/new', jobpack))
        if status != 'ok':
            raise DiscoError("Failed to start a job. Server replied: " + response)
        self.name = response
        return self