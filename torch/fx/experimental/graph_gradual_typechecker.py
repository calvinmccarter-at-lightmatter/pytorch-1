from functools import reduce
import torch
from torch.fx.tensor_type import Dyn, is_consistent, TensorType, is_more_precise
import operator


class GraphTypeChecker:
    def __init__(self, env, traced):
        self.env = env
        self.traced = traced

    def type_check(self):
        """
        A gradual type checker for graphs
        Effect: every node's field type will be
        populated with a type after type-checking is done
        """
        # here we collect types for variables
        graph = self.traced.graph

        # type check every node with gradual type rules
        # if any node does not type check return false
        for n in graph.nodes:
            if not self.type_check_node(n):
                return False
        return True

    def type_check_node(self, n):
        """
        Type check a given node.
        Current operations:
        - Reshape
        - Transpose
        - Add
        """
        if n.op == 'placeholder':
            if n.type is None:
                n.type = Dyn
            else:
                return n.type

        if n.op == 'call_function':
            if n.target == torch.add or n.target == operator.add:

                t1 = n.args[0].type
                t2 = n.args[1].type

                if is_consistent(t1, t2):
                    # we return the more precise type
                    if is_more_precise(t1, t2):
                        n.type = t1
                    else:
                        n.type = t2
                    return n.type
                else:
                    return False

            if n.target == torch.reshape:
                t1 = n.args[0].type
                t2 = n.args[1]
                t2_type = TensorType([Dyn if elem == -1 else elem for elem in t2])

                # if we do not know the original tensor dimension,
                # we return the required dimension
                if t1 == Dyn:
                    n.type = t2_type
                    return t2_type

                # if any of the dimensions are unknown,
                # we check for divisibility
                if isinstance(t1, TensorType) and Dyn in t1.__args__ or -1 in t2:
                    a = [e if e != Dyn else 1 for e in t1.__args__]
                    p1 = reduce(lambda x, y: x * y, a)
                    p2 = reduce(lambda x, y: x * y, t2)
                    if p1 % p2 == 0 or p2 % p1 == 0:
                        n.type = t2_type
                        return t2_type
                    else:
                        return False

                # if all dimensions are known we check the products
                if isinstance(t1, TensorType):
                    p1 = reduce(lambda x, y: x * y, t1.__args__)
                    p2 = reduce(lambda x, y: x * y, t2)
                    if p1 == p2:
                        n.type = t2_type
                        return t2_type
                    else:
                        return False

                else:
                    return False

            if n.target == torch.transpose:
                t = n.args[0].type
                dim1, dim2 = n.args[1], n.args[2]

                if 0 <= dim1 < len(t.__args__) and 0 <= dim2 < len(t.__args__):
                    new_type = list(t.__args__)
                    new_type[dim1], new_type[dim2] = new_type[dim2], new_type[dim1]
                    final = TensorType(new_type)
                    n.type = final
                    return n.type
                else:
                    return False
            else:
                raise NotImplementedError("Method for " + n.node + " not yet implemented")

        if n.op == 'output':
            n.type = n.args[0].type
            return n.type

        else:
            raise NotImplementedError("Method for " + n.node + " not yet implemented")
