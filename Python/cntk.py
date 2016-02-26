#
# CNTK proxy that translates Keras graphs into a CNTK configuration file.
#

import os
from keras.backend.common import _FLOATX, _EPSILON
import numpy as np

CNTK_TRAIN_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "cntk_train_template.cntk")
CNTK_PREDICT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "cntk_predict_template.cntk")

if "CNTK_EXECUTABLE_PATH" not in os.environ:
    raise ValueError("you need to point environmental variable 'CNTK_EXECUTABLE_PATH' to the CNTK binary")

CNTK_EXECUTABLE_PATH = os.environ['CNTK_EXECUTABLE_PATH']

class Context(object):
    def __init__(self, model):
        self.directory = os.path.abspath('_cntk_%s'%id(model))
        if os.path.exists(self.directory):
            print("Directory '%s' already exists - overwriting data."%self.directory) 
        else:
            os.mkdir(self.directory)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

class Node(object):
    def __init__(self, name, params=None, value=None, get_output_shape=None,
            var_name=None, check=None):
        self.name = name
        self.params = params
        self.value = value
        self.get_output_shape = get_output_shape
        self.var_name = var_name

        if check:
            #print("name=%s params=%s"%(name, str(params)))
            assert check(*params)

    def __add__(self, other):
        return Operator("Plus", (self, other),
                get_output_shape=lambda a,b: a.get_shape(),
                check=plus_check
                )

    def __radd__(self, other):
        return Operator("Plus", (other, self),
                get_output_shape=lambda a,b: a.get_shape(),
                check=plus_check
                )

    def __mul__(self, other):
        return times(self, other)

    def __truediv__(self, other):
        return Operator("**Divide**", (self, other),
                get_output_shape=lambda a,b: np.asarray(a).shape
                )

    def __rtruediv__(self, other):
        return Operator("**Divide**", (other, self),
                get_output_shape=lambda a,b: np.asarray(a).shape
                )

    def get_cntk_param_string(self, param_variable_names=None):
        return ""

    #def get_cntk_repr(self):
        #return self.

    def get_value(self):
        return self.value

    def get_shape(self):
        if self.value is not None:
            return self.value.shape
        else:
            if self.params:
                print("params: "+str(self.params))

                return self.get_output_shape(*self.params)
            else:
                return self.get_output_shape()

    def eval(self, **kw):
        raise NotImplementedError

    def __str__(self):
        return "%s / params=%s / value=%s"%(self.name, self.params, self.value)

# Because CNTK stores the sample in a transposed form, we need to
# switch parameters for some operators
BIN_OPS_WITH_REVERSED_PARAMETERS = {'Times'}

class Operator(Node):
    def __init__(self, name, params, **kwargs):
        super(Operator, self).__init__(name, params, **kwargs)

    def get_cntk_param_string(self, param_variable_names=None):
        if len(param_variable_names)==0:
            raise ValueError("expected one or more parameter variable names")

        if self.name in BIN_OPS_WITH_REVERSED_PARAMETERS: 
            assert len(param_variable_names)==2 # not sure what to do otherwise
            param_variable_names = reversed(param_variable_names)

        params = ", ".join(param_variable_names) if self.params is not None else ""

        return params


class Input(Node):
    def __init__(self, shape, **kwargs):
        super(Input, self).__init__('Input', **kwargs)
        self.get_output_shape=lambda : shape

    def get_cntk_param_string(self, param_variable_names=None):
        if len(param_variable_names)!=0:
            raise ValueError("expected no parameter variable names",
                    param_variable_names)

        if self.var_name == 'labels':
            params = "$NumOfClasses$, 1"
        elif self.var_name == 'features':
            params = "$FeatureDimension$, 1"

        return params

class LearnableParameter(Node):
    def __init__(self, **kwargs):
        super(LearnableParameter, self).__init__('LearnableParameter', **kwargs)
        self.get_output_shape=lambda : kwargs['value'].shape

    def get_cntk_param_string(self, param_variable_names=None):
        if len(param_variable_names)!=0:
            raise ValueError("expected no parameter variable names",
                    param_variable_names)

        shape = self.get_output_shape()

        # TODO this makes only sense as the first layer for a
        # classification problem.
        if len(shape)==1:
            params = "$NumOfClasses$" 
        elif len(shape)==2:
            # TODO have layer's output_dim and input_dim a word on this
            rows = shape[0] 
            cols = shape[0]
            params = "%s, %s"%(rows, cols)
        else:
            raise ValueError("expected either 1 or 2-dimensional shape", shape) 

        return params

def placeholder(shape):
    return Input(shape, var_name="features")

def variable(value, dtype=_FLOATX, name=None):
    value = np.asarray(value, dtype=dtype)
    node = LearnableParameter(value=value, get_output_shape=lambda: value.shape)
    return node

def plus_check(a,b):
    if not hasattr(a, 'get_shape') or not hasattr(b, 'get_shape'):
        return True

    a_shape = a.get_shape()
    b_shape = b.get_shape()

    if not a_shape or not b_shape:
        return True

    if a_shape[0]==None and len(b_shape)==1 and a_shape[1]==b_shape[0]:
        return True

    return a_shape==b_shape

def times_check(a,b):
    a_shape = a.get_shape()
    b_shape = b.get_shape()
    if not a_shape or not b_shape:
        return True

    return a_shape[1]==b_shape[0]

def times(left, right):
    return Operator("Times", (left, right),
            get_output_shape=lambda a,b: (a.get_shape()[0], b.get_shape()[1]),
            check=times_check
            )

def argmax(x, axis):
    # TODO axis
    return Operator("**ArgMax**", (x,))

# nn
def ssh(x):
    return x.get_shape()

def softmax(x):
    return Operator("Softmax", (x,), 
            get_output_shape=lambda x: x.get_shape()
            )

# other
def equal(a, b):
    return Operator("**Equal**", (a,b))

