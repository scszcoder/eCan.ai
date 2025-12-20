import { Emitter } from '@flowgram.ai/free-layout-editor';

import { CommentEditorEventParams } from './type';
import { CommentEditorDefaultValue, CommentEditorEvent } from './constant';

export class CommentEditorModel {
  private innerValue: string = CommentEditorDefaultValue;

  private emitter: Emitter<CommentEditorEventParams> = new Emitter();

  private editor: HTMLTextAreaElement;

  /** RegisterEvent */
  public on = this.emitter.event;

  /** GetWhen前Value */
  public get value(): string {
    return this.innerValue;
  }

  /** ExternalSettings模型Value */
  public setValue(value: string = CommentEditorDefaultValue): void {
    if (!this.initialized) {
      return;
    }
    if (value === this.innerValue) {
      return;
    }
    this.innerValue = value;
    this.syncEditorValue();
    this.emitter.fire({
      type: CommentEditorEvent.Change,
      value: this.innerValue,
    });
  }

  public set element(el: HTMLTextAreaElement) {
    if (this.initialized) {
      return;
    }
    this.editor = el;
  }

  /** GetEdit器 DOM 节点 */
  public get element(): HTMLTextAreaElement | null {
    return this.editor;
  }

  /** Edit器聚焦/失焦 */
  public setFocus(focused: boolean): void {
    if (!this.initialized) {
      return;
    }
    if (focused && !this.focused) {
      this.editor.focus();
    } else if (!focused && this.focused) {
      this.editor.blur();
      this.deselect();
      this.emitter.fire({
        type: CommentEditorEvent.Blur,
      });
    }
  }

  /** Select末尾 */
  public selectEnd(): void {
    if (!this.initialized) {
      return;
    }
    // Get文本Length
    const length = this.editor.value.length;
    // 将SelectRangeSettings为文本末尾(开始Position和结束Position都是文本Length)
    this.editor.setSelectionRange(length, length);
  }

  /** Get聚焦Status */
  public get focused(): boolean {
    return document.activeElement === this.editor;
  }

  /** CancelSelect文本 */
  private deselect(): void {
    const selection: Selection | null = window.getSelection();

    // 清除AllSelect区域
    if (selection) {
      selection.removeAllRanges();
    }
  }

  /** 是否Initialize */
  private get initialized(): boolean {
    return Boolean(this.editor);
  }

  /**
   * SyncEdit器实例Content
   * > **NOTICE:** *为确保不影响Performance，应仅在ExternalValue变更导致Edit器Value与模型Value不一致时调用*
   */
  private syncEditorValue(): void {
    if (!this.initialized) {
      return;
    }
    this.editor.value = this.innerValue;
  }
}
