/* eslint-disable @typescript-eslint/naming-convention -- enum */

export enum CommentEditorFormField {
  Size = 'size',
  Note = 'note',
}

/** Edit器Event */
export enum CommentEditorEvent {
  /** Content变更Event */
  Change = 'change',
  /** 多选Event */
  MultiSelect = 'multiSelect',
  /** 单选Event */
  Select = 'select',
  /** 失焦Event */
  Blur = 'blur',
}

export const CommentEditorDefaultValue = '';
