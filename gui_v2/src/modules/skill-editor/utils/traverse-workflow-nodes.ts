export function getNestedWorkflowNodes(node: any): any[][] {
  const groups: any[][] = [];

  if (Array.isArray(node?.data?.subcanvas?.nodes) && node.data.subcanvas.nodes.length > 0) {
    groups.push(node.data.subcanvas.nodes);
  }

  if (Array.isArray(node?.blocks) && node.blocks.length > 0) {
    groups.push(node.blocks);
  }

  return groups;
}

export function traverseWorkflowNodes(nodes: any[] | undefined, visitor: (node: any) => void): void {
  if (!Array.isArray(nodes) || nodes.length === 0) {
    return;
  }

  nodes.forEach((node) => {
    visitor(node);
    getNestedWorkflowNodes(node).forEach((children) => {
      traverseWorkflowNodes(children, visitor);
    });
  });
}
