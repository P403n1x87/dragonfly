#define PY_SSIZE_T_CLEAN
#include <Python.h>

#if PY_VERSION_HEX < 0x030c0000
#if defined __GNUC__ && defined HAVE_STD_ATOMIC
#undef HAVE_STD_ATOMIC
#endif
#define Py_BUILD_CORE
#include <internal/pycore_pystate.h>

#define HEAD_LOCK(runtime) \
    PyThread_acquire_lock((runtime)->interpreters.mutex, WAIT_LOCK)
#define HEAD_UNLOCK(runtime) \
    PyThread_release_lock((runtime)->interpreters.mutex)
#endif

#include <frameobject.h>
#if PY_VERSION_HEX >= 0x030b0000
#include <internal/pycore_frame.h>
#endif

// ----------------------------------------------------------------------------
static PyObject *
replace_constants(PyObject *m, PyObject *args)
{
    PyCodeObject *code = NULL;
    PyObject *consts = NULL;

    if (!PyArg_ParseTuple(args, "O!O!", &PyCode_Type, &code, &PyTuple_Type, &consts))
        return NULL;

    if (PyTuple_Size(consts) != PyTuple_Size(code->co_consts))
    {
        PyErr_SetString(PyExc_ValueError, "Constants tuple size mismatch");
        return NULL;
    }

    Py_DECREF(code->co_consts);
    Py_INCREF(consts);

    code->co_consts = consts;

    Py_RETURN_NONE;
}

// ----------------------------------------------------------------------------
static PyObject *
get_stack(PyObject *m, PyObject *args)
{
    PyFrameObject *frame = NULL;
    PyObject *stack = NULL;

    if (!PyArg_ParseTuple(args, "O!", &PyFrame_Type, &frame))
        return NULL;

#if PY_VERSION_HEX >= 0x030b0000
    Py_ssize_t stack_size = frame->f_frame->stacktop - frame->f_frame->f_code->co_nlocalsplus;
#elif PY_VERSION_HEX >= 0x030a0000
    Py_ssize_t stack_size = frame->f_stackdepth;
#else
    Py_ssize_t stack_size = frame->f_stacktop - frame->f_valuestack;
#endif

    stack = PyDict_New();
    if (stack == NULL)
        return NULL;

    // Pass the stack size vis the -1 key. Any gaps in the dict represent NULL
    // values.
    PyDict_SetItem(stack, PyLong_FromLong(-1), PyLong_FromLong(stack_size));

    for (int i = 0; i < stack_size; i++)
    {
#if PY_VERSION_HEX >= 0x030b0000
        _PyInterpreterFrame *iframe = frame->f_frame;
        PyObject *item = iframe->localsplus[iframe->f_code->co_nlocalsplus + i];
#elif PY_VERSION_HEX >= 0x030a0000
        PyObject *item = frame->f_valuestack[i];
#else
        PyObject *item = frame->f_valuestack[i];
#endif
        if (item == NULL)
            continue;

        PyDict_SetItem(stack, PyLong_FromLong(i), item);
    };

    return stack;
}

// ----------------------------------------------------------------------------
static PyObject *
replace_in_tuple(PyObject *m, PyObject *args)
{
    PyObject *tuple = NULL;
    PyObject *item = NULL;
    PyObject *replacement = NULL;

    if (!PyArg_ParseTuple(args, "O!OO", &PyTuple_Type, &tuple, &item, &replacement))
        return NULL;

    for (Py_ssize_t i = 0; i < PyTuple_Size(tuple); i++)
    {
        PyObject *current = PyTuple_GetItem(tuple, i);
        if (current == item)
        {
            Py_DECREF(current);
            // !!! DANGER !!!
            PyTuple_SET_ITEM(tuple, i, replacement);
            Py_INCREF(replacement);
        }
    }

    Py_RETURN_NONE;
}

#if PY_VERSION_HEX < 0x03090000
// ----------------------------------------------------------------------------
static int
_PyEval_SetTrace(PyThreadState *tstate, Py_tracefunc func, PyObject *arg)
{
    PyObject *temp = tstate->c_traceobj;
    _PyRuntimeState *runtime = &_PyRuntime;

    runtime->ceval.tracing_possible += (func != NULL) - (tstate->c_tracefunc != NULL);
    Py_XINCREF(arg);
    tstate->c_tracefunc = NULL;
    tstate->c_traceobj = NULL;
    /* Must make sure that profiling is not ignored if 'temp' is freed */
    tstate->use_tracing = tstate->c_profilefunc != NULL;
    Py_XDECREF(temp);
    tstate->c_tracefunc = func;
    tstate->c_traceobj = arg;
    /* Flag that tracing or profiling is turned on */
    tstate->use_tracing = ((func != NULL) || (tstate->c_profilefunc != NULL));

    return 0;
}
#endif

#if PY_VERSION_HEX < 0x030c0000
// ----------------------------------------------------------------------------
// Taken from the CPython 3.12 implementation of threading.settrace_all_threads.
static PyObject *
propagate_trace(PyObject *m, PyObject *arg)
{
    PyThreadState *this_tstate = _PyThreadState_GET();
    PyInterpreterState *interp = this_tstate->interp;

    // Assume that the tracefunc we want to set on all threads has been
    // set on the current thread with sys.settrace.
    Py_tracefunc tracefunc = this_tstate->c_tracefunc;
    PyObject *argument = this_tstate->c_traceobj;

    _PyRuntimeState *runtime = &_PyRuntime;
    HEAD_LOCK(runtime);
    PyThreadState *ts = PyInterpreterState_ThreadHead(interp);
    HEAD_UNLOCK(runtime);

    while (ts)
    {
        if (ts != this_tstate)
        {
            if (_PyEval_SetTrace(ts, tracefunc, argument) < 0)
            {
                PyErr_SetString(PyExc_RuntimeError, "Failed to set trace function");
                return NULL;
            }
        }

        HEAD_LOCK(runtime);
        ts = PyThreadState_Next(ts);
        HEAD_UNLOCK(runtime);
    }

    Py_RETURN_NONE;
}
#endif

// ----------------------------------------------------------------------------
static PyMethodDef code_methods[] = {
    {"replace_constants", replace_constants, METH_VARARGS, "Replace the tuple bearing the code constants."},
    {"get_stack", get_stack, METH_VARARGS, "Get the stack of a frame."},
    {"replace_in_tuple", replace_in_tuple, METH_VARARGS, "Replace an item in a tuple."},
#if PY_VERSION_HEX < 0x030c0000
    {"propagate_trace", propagate_trace, METH_NOARGS, "Propagate the current trace function to all threads."},
#endif
    {NULL, NULL, 0, NULL} /* Sentinel */
};

// ----------------------------------------------------------------------------
static struct PyModuleDef codemodule = {
    PyModuleDef_HEAD_INIT,
    "_maxilla", /* name of module */
    NULL,       /* module documentation, may be NULL */
    -1,         /* size of per-interpreter state of the module,
                   or -1 if the module keeps state in global variables. */
    code_methods,
};

// ----------------------------------------------------------------------------
PyMODINIT_FUNC
PyInit__maxilla(void)
{
    PyObject *m;

    m = PyModule_Create(&codemodule);
    if (m == NULL)
        return NULL;

    return m;
}
