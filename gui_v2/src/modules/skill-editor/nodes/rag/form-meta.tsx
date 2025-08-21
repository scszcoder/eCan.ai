import { Select, Radio, InputNumber, TextArea } from "@douyinfe/semi-ui";
import { Field, FieldRenderProps, FormMeta, FormRenderProps, ValidateTrigger } from "@flowgram.ai/free-layout-editor";
import { FormContent, FormHeader, FormItem } from "../../form-components";
import { FormCallable } from "../../form-components/form-callable";
import { createInferInputsPlugin, DisplayOutputs } from "@flowgram.ai/form-materials";
import { defaultFormMeta } from "../default-form-meta";
import { FlowNodeJSON } from "../../typings";
import type { IFlowConstantRefValue } from "@flowgram.ai/runtime-interface";

const knowledgeBases = [
  { label: "Default Knowledge Base", value: "default" },
  { label: "Product Documentation", value: "product_docs" },
  { label: "Customer Support KB", value: "support_kb" },
  { label: "Technical Wiki", value: "tech_wiki" },
  { label: "Company Policies", value: "company_policies" },
  { label: "Training Materials", value: "training_materials" },
  { label: "Research Papers", value: "research_papers" },
  { label: "Code Documentation", value: "code_docs" },
];

const retrievalModes = [
  { label: "Vector Search", value: "vector" },
  { label: "Keyword Search", value: "keyword" },
  { label: "Hybrid Search", value: "hybrid" },
];

const embeddingModels = [
  { label: "text-embedding-ada-002", value: "text-embedding-ada-002" },
  { label: "text-embedding-3-small", value: "text-embedding-3-small" },
  { label: "text-embedding-3-large", value: "text-embedding-3-large" },
  { label: "BAAI/bge-small-zh", value: "BAAI/bge-small-zh" },
  { label: "BAAI/bge-base-zh", value: "BAAI/bge-base-zh" },
  { label: "BAAI/bge-large-zh", value: "BAAI/bge-large-zh" },
  { label: "moka-ai/m3e-base", value: "moka-ai/m3e-base" },
  { label: "moka-ai/m3e-large", value: "moka-ai/m3e-large" },
];

type ConstantRef = IFlowConstantRefValue;

export const FormRender = (_props: FormRenderProps<FlowNodeJSON>) => {
  return (
    <>
      <FormHeader />
      <FormContent>
        <div>
          <Field name="inputsValues.knowledgeBase">
            {({ field }: FieldRenderProps<ConstantRef>) => (
              <FormItem name="Knowledge Base" type="string">
                <Select
                  value={String(field.value?.content ?? '')}
                  onChange={(value) => field.onChange({ type: 'constant', content: String(value ?? '') })}
                  optionList={knowledgeBases}
                  placeholder="Select knowledge base"
                />
              </FormItem>
            )}
          </Field>
          <Field name="inputsValues.retrievalMode">
            {({ field }: FieldRenderProps<ConstantRef>) => (
              <FormItem name="Retrieval Mode" type="string">
                <Radio.Group
                  value={String(field.value?.content ?? '')}
                  onChange={(e) => field.onChange({ type: 'constant', content: e.target.value })}
                >
                  {retrievalModes.map(mode => (
                    <Radio key={mode.value} value={mode.value}>{mode.label}</Radio>
                  ))}
                </Radio.Group>
              </FormItem>
            )}
          </Field>
          <Field name="inputsValues.topK">
            {({ field }: FieldRenderProps<ConstantRef>) => (
              <FormItem name="Top-K" type="number">
                <InputNumber
                  min={1}
                  max={20}
                  value={typeof field.value?.content === 'number' ? field.value.content : undefined}
                  onChange={(value) => field.onChange({ type: 'constant', content: typeof value === 'number' ? value : 0 })}
                />
              </FormItem>
            )}
          </Field>
          <Field name="inputsValues.scoreThreshold">
            {({ field }: FieldRenderProps<ConstantRef>) => (
              <FormItem name="Score Threshold" type="number">
                <InputNumber
                  min={0}
                  max={1}
                  step={0.1}
                  value={typeof field.value?.content === 'number' ? field.value.content : undefined}
                  onChange={(value) => field.onChange({ type: 'constant', content: typeof value === 'number' ? value : 0 })}
                />
              </FormItem>
            )}
          </Field>
          <Field name="inputsValues.embeddingModel">
            {({ field }: FieldRenderProps<ConstantRef>) => (
              <FormItem name="Embedding Model" type="string">
                <Select
                  value={String(field.value?.content ?? '')}
                  onChange={(value) => field.onChange({ type: 'constant', content: String(value ?? '') })}
                  optionList={embeddingModels}
                  placeholder="Select embedding model"
                />
              </FormItem>
            )}
          </Field>
          <Field name="inputsValues.query">
            {({ field }: FieldRenderProps<ConstantRef>) => (
              <FormItem name="Query" type="string">
                <TextArea
                  value={String(field.value?.content ?? '')}
                  onChange={(value) => field.onChange({ type: 'constant', content: value })}
                  placeholder="Enter your search query"
                  rows={4}
                />
              </FormItem>
            )}
          </Field>
          <Field name="inputsValues.filters">
            {({ field }: FieldRenderProps<ConstantRef>) => (
              <FormItem name="Filters" type="string">
                <TextArea
                  value={String(field.value?.content ?? '')}
                  onChange={(value) => field.onChange({ type: 'constant', content: value })}
                  placeholder="Enter filter conditions in JSON format"
                  rows={2}
                />
              </FormItem>
            )}
          </Field>
          <FormCallable />
          <DisplayOutputs displayFromScope />
        </div>
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta = {
  render: (props) => <FormRender {...props} />,
  validateTrigger: ValidateTrigger.onChange,
  validate: defaultFormMeta.validate,
  effect: defaultFormMeta.effect,
  plugins: [
    createInferInputsPlugin({ sourceKey: 'inputsValues', targetKey: 'inputs' }),
  ],
};