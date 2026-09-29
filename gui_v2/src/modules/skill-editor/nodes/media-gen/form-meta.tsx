/**
 * Media Generation node form: image / video / speech via the eCan cloud proxy.
 * Only the fields relevant to the selected mediaType are shown; the model list
 * and per-model options come from the proxy's GET /models capabilities.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { AutoComplete, Checkbox, Divider, Input, InputNumber, Select, Typography } from '@douyinfe/semi-ui';
import { DisplayOutputs, createInferInputsPlugin } from '@flowgram.ai/form-materials';
import { defaultFormMeta } from '../default-form-meta';
import { FormContent, FormHeader, FormItem } from '../../form-components';
import { CollapsiblePromptEditor } from '../../form-components/CollapsiblePromptEditor';
import { useNodeRenderContext } from '../../hooks';
import { get_ipc_api } from '../../../../services/ipc_api';

type MediaType = 'image' | 'video' | 'speech';
type Capabilities = Record<string, any>;
interface MediaModel {
  id: string;
  capabilities?: Capabilities;
}

// GET /models `capabilities.endpoints` value per media type.
const ENDPOINTS: Record<MediaType, string> = { image: 'images', video: 'videos', speech: 'speech' };

// Models the CN proxy offers; used only when the live list is unavailable.
const MODEL_SUGGESTIONS: Record<MediaType, string[]> = {
  image: ['wan2.2-t2i-plus', 'qwen-image', 'wan2.5-i2i-preview'],
  video: ['wan2.2-t2v-plus', 'wan2.2-i2v-plus', 'wan2.5-t2v-preview', 'wan2.5-i2v-preview'],
  speech: ['cosyvoice-v2', 'qwen3-tts-flash'],
};

const TIMEOUT_PLACEHOLDER: Record<MediaType, number> = { image: 120, video: 900, speech: 60 };

const ASPECT_RATIOS = ['1:1', '16:9', '9:16', '4:3', '3:4'];
const RESOLUTIONS = ['480p', '720p', '1080p'];

// Fetched once per editor session (an empty answer is retried on the next mount).
let mediaModelsPromise: Promise<MediaModel[]> | null = null;

function fetchMediaModels(): Promise<MediaModel[]> {
  if (!mediaModelsPromise) {
    mediaModelsPromise = get_ipc_api()
      .executeRequest<{ models: MediaModel[] }>('media.list_models', {})
      .then((res) => {
        const rows = res?.data?.models;
        return Array.isArray(rows) ? rows.filter((m) => m && typeof m.id === 'string' && m.id) : [];
      })
      .catch((error) => {
        console.warn('[MediaGen] Failed to fetch media models:', error);
        return [] as MediaModel[];
      })
      .then((rows) => {
        if (!rows.length) mediaModelsPromise = null;
        return rows;
      });
  }
  return mediaModelsPromise;
}

const useMediaModels = (): MediaModel[] => {
  const [models, setModels] = useState<MediaModel[]>([]);
  useEffect(() => {
    let alive = true;
    fetchMediaModels().then((rows) => {
      if (alive) setModels(rows);
    });
    return () => {
      alive = false;
    };
  }, []);
  return models;
};

const modelsFor = (models: MediaModel[], type: MediaType): string[] => {
  const live = models
    .filter((m) => Array.isArray(m.capabilities?.endpoints) && m.capabilities!.endpoints.includes(ENDPOINTS[type]))
    .map((m) => m.id);
  return live.length ? live : MODEL_SUGGESTIONS[type];
};

const capabilitiesOf = (models: MediaModel[], modelName: string): Capabilities | undefined => {
  const caps = models.find((m) => m.id === modelName)?.capabilities;
  return caps && Object.keys(caps).length ? caps : undefined;
};

const listOf = (v: any): any[] | undefined => (Array.isArray(v) && v.length ? v : undefined);

const toTemplate = (val: any) => {
  if (val && typeof val === 'object' && 'content' in val) {
    const c = val.content;
    return { ...val, content: typeof c === 'string' ? c : c == null ? '' : String(c) };
  }
  return { type: 'template', content: val == null ? '' : String(val) };
};

export const FormRender = (_props: FormRenderProps<any>) => {
  const { t } = useTranslation('skillEditor');
  const { readonly } = useNodeRenderContext();
  const mediaModels = useMediaModels();
  const withDefault = (values: Array<string | number>) => [
    { label: t('nodes.mediaGen.default'), value: '' },
    ...values.map((v) => ({ label: String(v), value: v })),
  ];

  const stringField = (key: string, placeholder?: string) => (
    <FormItem name={key} label={t(`nodes.mediaGen.${key}`)} type="string" vertical>
      <Field<string> name={`inputsValues.${key}.content`}>
        {({ field }) => (
          <Input
            size="small"
            value={(field.value as string) ?? ''}
            onChange={(val) => field.onChange(val)}
            placeholder={placeholder}
            disabled={readonly}
          />
        )}
      </Field>
    </FormItem>
  );

  const numberField = (key: string, opts: { min?: number; max?: number; step?: number; placeholder?: string } = {}) => (
    <FormItem name={key} label={t(`nodes.mediaGen.${key}`)} type="number" vertical>
      <Field<number | string> name={`inputsValues.${key}.content`}>
        {({ field }) => (
          <InputNumber
            size="small"
            style={{ width: '100%' }}
            value={field.value === '' || field.value == null ? undefined : (field.value as number)}
            onChange={(val) => field.onChange(val === '' || val == null ? '' : Number(val))}
            min={opts.min}
            max={opts.max}
            step={opts.step}
            placeholder={opts.placeholder}
            disabled={readonly}
          />
        )}
      </Field>
    </FormItem>
  );

  const selectField = (key: string, options: Array<{ label: string; value: string | number }>) => (
    <FormItem name={key} label={t(`nodes.mediaGen.${key}`)} type="string" vertical>
      <Field<string | number> name={`inputsValues.${key}.content`}>
        {({ field }) => (
          <Select
            size="small"
            style={{ width: '100%' }}
            value={field.value as string | number}
            optionList={options}
            onChange={(val) => field.onChange(val as string | number)}
            disabled={readonly}
          />
        )}
      </Field>
    </FormItem>
  );

  // Free text with suggestions (e.g. voices the model lists).
  const suggestField = (key: string, suggestions: string[]) => (
    <FormItem name={key} label={t(`nodes.mediaGen.${key}`)} type="string" vertical>
      <Field<string> name={`inputsValues.${key}.content`}>
        {({ field }) => (
          <AutoComplete
            size="small"
            style={{ width: '100%' }}
            value={(field.value as string) ?? ''}
            data={suggestions}
            onChange={(val) => field.onChange(String(val ?? ''))}
            showClear
            disabled={readonly}
          />
        )}
      </Field>
    </FormItem>
  );

  const templateField = (key: string, label: string, help?: string) => (
    <FormItem name={key} label={label} type="string" vertical>
      <Field<any> name={`inputsValues.${key}`}>
        {({ field, fieldState }) => (
          <div style={{ width: '100%' }}>
            <CollapsiblePromptEditor
              value={toTemplate(field.value)}
              onChange={field.onChange}
              readonly={readonly}
              hasError={Object.keys(fieldState?.errors || {}).length > 0}
              defaultCollapsed={true}
              collapsedLines={3}
            />
            {help && (
              <Typography.Text type="tertiary" size="small">
                {help}
              </Typography.Text>
            )}
          </div>
        )}
      </Field>
    </FormItem>
  );

  return (
    <>
      <FormHeader />
      <FormContent>
        <Divider />
        <Field<string> name="inputsValues.mediaType.content">
          {({ field: mediaTypeField }) => (
            <Field<string> name="inputsValues.modelName.content">
              {({ field: modelField }) => {
                const mediaType = ((mediaTypeField.value as MediaType) || 'image') as MediaType;
                const modelName = (modelField.value as string) || '';
                const caps = capabilitiesOf(mediaModels, modelName);
                const showRefs = !caps || !!caps.reference_images;
                return (
                  <>
                    <FormItem name="mediaType" label={t('nodes.mediaGen.mediaType')} type="string" vertical required>
                      <Select
                        size="small"
                        style={{ width: '100%' }}
                        value={mediaType}
                        optionList={[
                          { label: t('nodes.mediaGen.mediaTypeImage'), value: 'image' },
                          { label: t('nodes.mediaGen.mediaTypeVideo'), value: 'video' },
                          { label: t('nodes.mediaGen.mediaTypeSpeech'), value: 'speech' },
                        ]}
                        onChange={(val) => {
                          const next = val as MediaType;
                          mediaTypeField.onChange(next);
                          // Switch the model to the new type's default unless the user typed a custom one
                          const known = (['image', 'video', 'speech'] as MediaType[]).some(
                            (type) => MODEL_SUGGESTIONS[type].includes(modelName) || modelsFor(mediaModels, type).includes(modelName),
                          );
                          const nextModels = modelsFor(mediaModels, next);
                          if (!modelName || (known && !nextModels.includes(modelName))) {
                            const preferred = MODEL_SUGGESTIONS[next][0];
                            modelField.onChange(nextModels.includes(preferred) ? preferred : nextModels[0]);
                          }
                        }}
                        disabled={readonly}
                      />
                    </FormItem>

                    <FormItem name="modelName" label={t('nodes.mediaGen.modelName')} type="string" vertical required>
                      <AutoComplete
                        size="small"
                        style={{ width: '100%' }}
                        value={modelName}
                        data={modelsFor(mediaModels, mediaType)}
                        onChange={(val) => modelField.onChange(String(val ?? ''))}
                        showClear
                        disabled={readonly}
                      />
                    </FormItem>

                    {templateField(
                      'prompt',
                      mediaType === 'speech' ? t('nodes.mediaGen.speechText') : t('nodes.mediaGen.prompt'),
                    )}

                    {mediaType !== 'speech' && stringField('negativePrompt')}
                    {mediaType !== 'speech' && showRefs &&
                      templateField('referenceImages', t('nodes.mediaGen.referenceImages'), t('nodes.mediaGen.referenceImagesHelp', { skipInterpolation: true }))}

                    {mediaType === 'image' && (
                      <>
                        {listOf(caps?.sizes) ? selectField('size', withDefault(caps!.sizes)) : stringField('size', '1024*1024')}
                        {selectField('aspectRatio', withDefault(ASPECT_RATIOS))}
                        {numberField('n', { min: 1, max: Number(caps?.max_images) || 4, step: 1 })}
                      </>
                    )}

                    {mediaType === 'video' && (
                      <>
                        {(!caps || caps.image_to_video) &&
                          templateField('firstFrame', t('nodes.mediaGen.firstFrame'), t('nodes.mediaGen.firstFrameHelp', { skipInterpolation: true }))}
                        {caps?.last_frame &&
                          templateField('lastFrame', t('nodes.mediaGen.lastFrame'), t('nodes.mediaGen.lastFrameHelp', { skipInterpolation: true }))}
                        {listOf(caps?.durations)
                          ? selectField('durationSeconds', withDefault(caps!.durations))
                          : numberField('durationSeconds', { min: 1, step: 1 })}
                        {selectField('resolution', withDefault(listOf(caps?.resolutions) || RESOLUTIONS))}
                        {selectField('aspectRatio', withDefault(listOf(caps?.aspect_ratios) || ASPECT_RATIOS))}
                        {caps?.generates_audio === 'optional' && (
                          <FormItem name="generateAudio" label={t('nodes.mediaGen.generateAudio')} type="boolean" vertical>
                            <Field<boolean> name="inputsValues.generateAudio.content">
                              {({ field }) => (
                                <Checkbox
                                  checked={!!field.value}
                                  onChange={(e: any) => field.onChange(e.target?.checked ?? e)}
                                  disabled={readonly}
                                >
                                  {t('nodes.mediaGen.generateAudioDesc')}
                                </Checkbox>
                              )}
                            </Field>
                          </FormItem>
                        )}
                      </>
                    )}

                    {mediaType === 'speech' && (
                      <>
                        {suggestField('voice', listOf(caps?.voices) || [])}
                        {selectField('audioFormat', withDefault(listOf(caps?.formats) || ['mp3', 'wav']))}
                        {numberField('speed', { min: 0.5, max: 2, step: 0.1 })}
                      </>
                    )}

                    {numberField('timeoutSeconds', { min: 1, step: 1, placeholder: String(TIMEOUT_PLACEHOLDER[mediaType]) })}
                    {stringField('outputSubdir', t('nodes.mediaGen.optional'))}
                  </>
                );
              }}
            </Field>
          )}
        </Field>
        <Typography.Text type="tertiary" size="small">
          {t('nodes.mediaGen.resultHint')}
        </Typography.Text>
        <Divider />
        <DisplayOutputs displayFromScope />
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta = {
  render: (props) => <FormRender {...props} />,
  effect: defaultFormMeta.effect,
  validate: defaultFormMeta.validate,
  plugins: [createInferInputsPlugin({ sourceKey: 'inputsValues', targetKey: 'inputs' })],
};
