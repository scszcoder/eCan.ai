import { WorkflowDocument } from '@flowgram.ai/free-layout-editor';

let workflowDocumentRef: WorkflowDocument | null = null;

export const setWorkflowDocumentRef = (document: WorkflowDocument | null) => {
  workflowDocumentRef = document;
};

export const getWorkflowDocumentRef = (): WorkflowDocument | null => workflowDocumentRef;
