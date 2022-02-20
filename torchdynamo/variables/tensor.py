import copy
import itertools
import operator
from typing import Dict
from typing import List

import torch.fx
import torch.random

from .. import config
from .. import variables
from ..utils import istype
from ..utils import product
from ..utils import proxy_args_kwargs
from ..utils import unimplemented
from .base import VariableTracker
from .base import typestr


class TensorVariable(VariableTracker):
    """A torch.Tensor input or an intermediate value in the FX graph"""

    _nonvar_fields = [
        "proxy",
        "dtype",
        "device",
        "ndim",
        "size",
        "stride",
        "requires_grad",
    ]

    @staticmethod
    def propagate_args_kwargs(node):
        def visit(n: torch.fx.Node):
            return n.meta["example_value"]

        return torch.fx.node.map_arg((node.args, node.kwargs), visit)

    @classmethod
    def create(cls, tx, proxy, example_value=None, nnmodule=None, **options):
        if "guards" in options:
            tx.output.guards.update(options["guards"])
        assert "example_value" not in proxy.node.meta
        if not config.dynamic_propagation:
            if isinstance(example_value, torch.Tensor):
                options.update(TensorVariable.specialize(example_value))
            return TensorVariable(proxy, **options)

        if example_value is None:
            rng = torch.clone(torch.random.get_rng_state())
            op = proxy.node.op
            args, kwargs = cls.propagate_args_kwargs(proxy.node)
            if op == "call_function":
                example_value = proxy.node.target(*args, **kwargs)
            elif op == "call_method":
                example_value = getattr(args[0], proxy.node.target)(*args[1:], **kwargs)
            elif op == "call_module":
                assert nnmodule is not None
                example_value = copy.deepcopy(nnmodule)(*args, **kwargs)
            else:
                assert False, op
            torch.random.set_rng_state(rng)

        if isinstance(example_value, torch.Tensor):
            proxy.node.meta["example_value"] = example_value.clone()
            options.update(TensorVariable.specialize(example_value))
            return TensorVariable(proxy, **options)
        elif isinstance(example_value, tuple):
            unpacked = []
            for i, val in enumerate(example_value):
                unpacked.append(
                    TensorVariable.create(
                        tx,
                        proxy.tracer.create_proxy(
                            "call_function", operator.getitem, (proxy, i), {}
                        ),
                        example_value=val,
                        **options,
                    )
                )
            if istype(example_value, tuple):
                return variables.TupleVariable(unpacked, **options)
            else:
                assert (
                    example_value.__class__.__module__ == "torch.return_types"
                    or hasattr(example_value, "_fields")
                ), "namedtuple?"
                return variables.NamedTupleVariable(
                    unpacked, example_value.__class__, **options
                )
        else:
            assert (
                False
            ), f"{typestr(example_value)} {proxy.node.op} {proxy.node.target}"

    def __init__(
        self,
        proxy: torch.fx.Proxy,
        dtype=None,
        device=None,
        ndim=None,
        size=None,
        stride=None,
        requires_grad=None,
        **kwargs,
    ):
        assert dtype is not None or not config.dynamic_propagation
        super(TensorVariable, self).__init__(**kwargs)
        self.proxy = proxy
        self.dtype = dtype
        self.device = device
        self.ndim = ndim
        self.size = size
        self.stride = stride
        self.requires_grad = requires_grad

    def as_proxy(self):
        return self.proxy

    def python_type(self):
        return torch.Tensor

    @staticmethod
    def specialize(value: torch.Tensor):
        props = {
            "dtype": value.dtype,
            "device": value.device,
            "ndim": int(value.ndim),
            "requires_grad": value.requires_grad,
        }
        if not config.dynamic_shapes:
            props["size"] = tuple(value.size())
            props["stride"] = tuple(value.stride())
        return props

    def get_var_attr(self, tx, name):
        from . import ConstantVariable
        from . import TorchVariable

        result = None
        options = VariableTracker.propagate(self)
        if name == "ndim" and self.ndim is not None:
            result = ConstantVariable(self.ndim, **options)
        elif name == "dtype" and self.dtype is not None:
            result = TorchVariable(self.dtype, **options)
        elif name == "device" and self.device is not None:
            result = TorchVariable(self.device, **options)
        elif name == "is_cuda" and self.device is not None:
            result = ConstantVariable(self.device.type == "cuda", **options)
        elif name == "shape" and self.size is not None:
            result = ConstantVariable(self.size, **options)
        elif name == "requires_grad" and self.requires_grad is not None:
            result = ConstantVariable(self.requires_grad, **options)
        elif name == "shape" and self.size is None:
            result = self.call_method(tx, "size", [], {})
        elif name == "ndim" and self.ndim is None:
            result = self.call_method(tx, "dim", [], {})

        if result is None:
            raise NotImplementedError()

        return result

    def call_method(
        self,
        tx,
        name,
        args: "List[VariableTracker]",
        kwargs: "Dict[str, VariableTracker]",
    ) -> "VariableTracker":
        from . import ConstantVariable
        from . import TupleVariable

        options = VariableTracker.propagate(self, args, kwargs.values())

        if name == "stride" and self.stride is not None:
            constant_result = ConstantVariable(self.stride, **options)
        elif name == "size" and self.size is not None:
            constant_result = ConstantVariable(self.size, **options)
        elif name == "numel" and self.size is not None:
            constant_result = ConstantVariable(product(self.size), **options)
        elif name in ("ndimension", "dim") and self.ndim is not None:
            constant_result = ConstantVariable(self.ndim, **options)
        elif name == "is_floating_point" and self.dtype is not None:
            constant_result = ConstantVariable(self.dtype.is_floating_point, **options)
        else:
            constant_result = None

        if constant_result:
            assert not kwargs
            if len(args) == 1:
                return constant_result.getitem_const(args[0])
            elif args:
                return TupleVariable(
                    [constant_result.getitem_const(a) for a in args], **options
                )
            return constant_result
        elif (
            name == "repeat"
            and not all(
                x.is_python_constant() for x in itertools.chain(args, kwargs.values())
            )
            and not config.dynamic_shapes
        ):
            unimplemented("dynamic Tensor.repeat")
        elif name in ("item", "tolist", "numpy", "nonzero"):
            unimplemented(f"Tensor.{name}")
        elif name == "__len__":
            if self.size:
                assert not config.dynamic_shapes
                return ConstantVariable(self.size[0], **options)
            else:
                return TensorVariable.create(
                    tx,
                    tx.output.create_proxy(
                        "call_function", len, (self.as_proxy(),), {}
                    ),
                    **options,
                )
        elif name == "__setitem__":
            tx.output.guards.update(options["guards"])
            tx.output.create_proxy(
                "call_function",
                operator.setitem,
                *proxy_args_kwargs([self] + args, kwargs),
            )
            return ConstantVariable(None, **options)
        else:
            return TensorVariable.create(
                tx,
                tx.output.create_proxy(
                    "call_method", name, *proxy_args_kwargs([self] + args, kwargs)
                ),
                **options,
            )
