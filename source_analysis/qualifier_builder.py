from typing import Dict
import javalang

def build_qualifier_map(cls_node, method_node) -> Dict[str, str]:
    """
    qualifier name → simple class name
    """
    qual_map = {}

    # 1) Method parameters
    for p in method_node.parameters:
        qual_map[p.name] = p.type.name

    # 2) Local variables 
    for _, decl in method_node.filter(javalang.tree.LocalVariableDeclaration):
        t = decl.type.name
        for var in decl.declarators:
            qual_map[var.name] = t

    # 3) Class‐level fields (if you ever refer to 'this.foo' in your setup)
    for field in cls_node.fields:
        t = (field.declarators[0].type.name
             if hasattr(field.declarators[0], "type")
             else field.type.name)
        for var in field.declarators:
            qual_map[var.name] = t

    return qual_map
