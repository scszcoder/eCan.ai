<template>
  <canvas id="canvas"></canvas>
  <div class="tool-top">
    <t-button variant="text" theme="primary" :disabled="imageIndex === 0" @click="last">
      <template #icon>
        <ArrowLeftIcon/>
      </template>
      {{ t('canvas.last') }}
    </t-button>
    <t-button variant="text" theme="primary" @click="save">{{ t('canvas.save') }}</t-button>
    <t-button variant="text" theme="primary" @click="next" :disabled="imageIndex >= image.length - 1">
      {{ t('canvas.next') }}
      <template #suffix>
        <ArrowRightIcon/>
      </template>
    </t-button>
  </div>
  <div class="tool-left">
    <input
        type="file"
        style="display:none"
        v-show="false"
        @change="handleFileUpload"
    />
    <div v-if="menu" class="menu">
      <t-space size="12px" direction="vertical">
        <div v-for="option in options" :key="option.type">
          <t-button :theme="currentType === option.type? 'primary' : 'default'" shape="circle"
                    @click="typeChange(option.type)">
            <template #icon>
              <icon :name="option.icon"/>
            </template>
          </t-button>
        </div>
      </t-space>
    </div>
    <t-button :theme="menu? 'danger':'primary'" shape="circle" @click="openMenu">
      <template #icon>
        <CloseIcon v-if="menu"/>
        <MenuApplicationIcon v-else/>
      </template>
    </t-button>
  </div>
  <div class="tool-right" :class="{'open-animate': showReightTool === 1, 'close-animate': showReightTool === 0}">
    <div class="close-btn">
      <t-button theme="danger" shape="circle" @click="closeTool">
        <template #icon>
          <CloseIcon/>
        </template>
      </t-button>
    </div>
    <div class="tool-right-content">
      <div class="tool-right-content-scroll">
        <t-form ref="form" :colon="true" :label-width="120" :rules="FORM_RULES" :label-align="'right'" :data="formData">
          <t-form-item :label="t('canvas.anchor')" name="anchor">
            <t-input v-model="formData.anchor" :placeholder="t('canvas.anchorPlaceholder')" :clearable="true"/>
          </t-form-item>
          <t-form-item :label="t('canvas.anchorType')" name="type">
            <t-select v-model="formData.type" class="demo-select-base" :placeholder="t('canvas.anchorTypePlaceholder')"
                      :clearable="true" :filterable="true">
              <t-option v-for="(item, index) in anchorType" :key="index" :value="item.value" :label="item.label">
                {{ item.label }}
              </t-option>
            </t-select>
          </t-form-item>
          <t-form-item v-if="formData.type==='text'" :label="t('canvas.template')" name="template">
            <t-input v-model="formData.template" :placeholder="t('canvas.templatePlaceholder')" :clearable="true"/>
          </t-form-item>
          <t-form-item :label="t('canvas.method')" name="method">
            <t-select v-model="formData.method" :placeholder="t('canvas.methodPlaceholder')"
                      :clearable="true" :filterable="true">
              <t-option v-for="(item, index) in method" :key="index" :value="item.value" :label="item.label">
                {{ item.label }}
              </t-option>
            </t-select>
          </t-form-item>
          <div v-for="(loca, index) in formData.location" class="t-form-location" @mouseenter="handleMouseEnter(index)"
               @mouseleave="handleMouseLeave(index)">
            <div class="t-form-close" v-if="loca.showClose">
              <t-button theme="default" size="extra-small" @click="handleOpenDialog" shape="circle">
                <template #icon>
                  <CloseIcon size="extra-small"/>
                </template>
              </t-button>
            </div>
            <t-divider>
              {{ t('canvas.relactionAnchor') + ' ' + (index + 1) }}
            </t-divider>
            <t-form-item :label="t('canvas.anchor')" :name="`location[${index}].relaction`">
              <t-select v-model="loca.relaction" class="demo-select-base"
                        :placeholder="t('canvas.relactionPlaceholder')"
                        :clearable="true" :filterable="true">
                <t-option v-for="(item, index) in relactionAnchor" :key="index" :value="item.uuid" :label="item.anchor">
                  {{ item.anchor }}
                </t-option>
              </t-select>
            </t-form-item>
            <t-form-item :label="t('canvas.side')" :name="`location[${index}].side`">
              <t-select v-model="loca.side" class="demo-select-base" :placeholder="t('canvas.sidePlaceholder')"
                        :clearable="true" :filterable="true">
                <t-option v-for="(item, index) in side" :key="index" :value="item.value" :label="item.label">
                  {{ item.label }}
                </t-option>
              </t-select>
            </t-form-item>
            <t-form-item :label="t('canvas.dir')" :name="`location[${index}].dir`">
              <t-select v-model="loca.dir" class="demo-select-base" :placeholder="t('canvas.dirPlaceholder')"
                        :clearable="true" :filterable="true">
                <t-option v-for="(item, index) in dir" :key="index" :value="item.value" :label="item.label">
                  {{ item.label }}
                </t-option>
              </t-select>
            </t-form-item>
            <t-form-item :label="t('canvas.offset')" :name="`location[${index}].offset`">
              <t-input-number :min="1" style="width: 16rem" v-model="loca.offset" theme="column"
                              :placeholder="t('canvas.offsetPlaceholder')" :clearable="true"/>
            </t-form-item>

            <t-form-item :label="t('canvas.offsetUnit')" :name="`location[${index}].offsetUnit`">
              <t-select v-model="loca.offsetUnit" class="demo-select-base"
                        :placeholder="t('canvas.offsetUnitPlaceholder')"
                        :clearable="true" :filterable="true">
                <t-option v-for="(item, index) in offsetUnit" :key="index" :value="item.value" :label="item.label">
                  {{ item.label }}
                </t-option>
              </t-select>
            </t-form-item>
          </div>
          <div class="t-form-button">
            <t-button size="small" theme="default" @click="handleRelationAnchor">{{
                t('canvas.relactionAnchor')
              }}
            </t-button>
          </div>
        </t-form>
      </div>

      <div class="tool-right-footer">
        <t-space size="small">
          <t-button theme="primary" @click="onSubmit">{{ t('canvas.submit') }}</t-button>
          <t-button theme="default" variant="base" @click="onReset">{{ t('canvas.reset') }}</t-button>
        </t-space>
      </div>
    </div>
  </div>
  <t-dialog
      v-model:visible="showDeleteDialog"
      theme="info"
      :header="t('canvas.tips')"
      :body="t('canvas.confirmDeleteMessage')"
      :cancel-btn="t('canvas.cancelDelete')"
      :confirm-btn="t('canvas.confirmDelete')"
      @confirm="handleClose"
  />
</template>

<script setup lang="ts">
import {fabric} from 'fabric';
import {nextTick, onBeforeUnmount, onMounted, reactive, ref} from "vue";
import {ArrowLeftIcon, ArrowRightIcon, CloseIcon, Icon, MenuApplicationIcon} from "tdesign-icons-vue-next";
import {FormInstanceFunctions, FormProps, MessagePlugin} from "tdesign-vue-next";
import {useI18n} from 'vue-i18n';
import _ from 'lodash';
import {useRoute} from "vue-router";
import {
  addRectLabel,
  closeTool,
  currentType,
  findObject,
  form,
  formData,
  formReset,
  handleClose,
  handleFileUpload,
  handleKeyDown,
  handleMouseEnter, handleMouseLeave,
  handleOpenDialog,
  image,
  imageIndex,
  init,
  last,
  next,
  save,
  selectionObject,
  showDeleteDialog,
  showReightTool,
  typeChange
} from "@/views/skill/canvas/index";

const {t, locale} = useI18n()
const route = useRoute();


const relactionAnchor = ref<{
  anchor: string,
  uuid: string
}[]>([]) //可关联锚点信息


const FORM_RULES: FormProps['rules'] = {
  anchor: [
    {required: true, message: t('canvas.anchorError'), trigger: 'change', type: 'warning'},
    {required: true, message: t('canvas.anchorError'), trigger: 'blur', type: 'warning'}
  ],
  type: [
    {required: true, message: t('canvas.anchorTypeError'), trigger: 'change', type: 'warning'},
  ],
  method: [
    {required: true, message: t('canvas.methodError'), trigger: 'change', type: 'warning'},
  ],
  relaction: [
    {required: true, message: t('canvas.relactionError'), trigger: 'change', type: 'warning'},
  ],
  side: [
    {required: true, message: t('canvas.sideError'), trigger: 'change', type: 'warning'},
  ],
  dir: [
    {required: true, message: t('canvas.dirError'), trigger: 'change', type: 'warning'},
  ],
  offset: [
    {required: true, message: t('canvas.offsetError'), trigger: 'change', type: 'warning'},
    {required: true, message: t('canvas.offsetError'), trigger: 'blur', type: 'warning'}
  ],
  offsetUnit: [
    {required: true, message: t('canvas.offsetUnitError'), trigger: 'change', type: 'warning'},
  ]
};


const anchorType = [
  {value: 'text', label: t('canvas.text')},
  {value: 'icon', label: t('canvas.icon')}
]

const method = [
  {value: '0', label: t('canvas.textOrIcon')},
  {value: '1', label: t('canvas.polyganShape')},
  {value: '2', label: t('canvas.line')},
  {value: '3', label: t('canvas.anchorGroup')}
]

const side = [
  {value: 'top', label: t('canvas.top')},
  {value: 'bottom', label: t('canvas.bottom')},
  {value: 'left', label: t('canvas.left')},
  {value: 'right', label: t('canvas.right')}
]

const dir = [
  {value: '>', label: '>'},
  {value: '<', label: '<'},
]

const offsetUnit = [
  {value: 'px', label: 'px'},
  {value: 'box', label: 'box'},
]

const handleRelationAnchor = () => {
  const allRect = findObject(fabric.Rect)
  const relaction = allRect?.filter((rect: any) => {
    // @ts-ignore
    const bool = rect.get('uuid') !== selectionObject.value![0].get('uuid');
    if (bool) {
      if (rect.formData) {
        const data = _.cloneDeep(rect.formData)
        relactionAnchor.value?.push(data)
      } else {
        return false
      }
    }
    return bool
  })
  if (relaction && relaction.length > 0) {
    formData.location.push({
      relaction: undefined,
      side: '',
      dir: '',
      offset: '',
      offsetUnit: '',
      showClose: false
    })
  } else {
    MessagePlugin.warning(t('canvas.notFoundRelaction'));
  }
}

const onSubmit = () => {
  if (form.value) {
    form.value.validate().then((validateResult) => {
      if (validateResult && Object.keys(validateResult).length) {
        console.log(validateResult)
        MessagePlugin.warning(t('canvas.validateMessage'));
      } else {
        MessagePlugin.success(t('canvas.submitMessage'));
        const data = _.cloneDeep(formData);
        const obj = selectionObject.value![0]
        // @ts-ignore
        obj.set('formData', data)
        addRectLabel(obj, formData.anchor)
        formReset()
        closeTool()
      }
    });
  }
};

const onReset = () => {
  formReset()
  MessagePlugin.success(t('canvas.resetMessage'));
};

const menu = ref(true)
const openMenu = () => {
  menu.value = !menu.value
}

const options = reactive([
  {type: 'select', icon: 'gesture-up', text: '选取'},
  {type: 'drag', icon: 'drag-move', text: '拖动'},
  {type: 'rect', icon: 'rectangle', text: '矩形'},
  {type: 'file', icon: 'upload', text: '上传'},
  {type: 'clear', icon: 'clear', text: '删除'}
])


onMounted(async () => {
  console.log(route.params)
  locale.value = route.params.lang as string
  sessionStorage.setItem('localeLang', route.params.lang as string)
  await nextTick(() => {
    init()
  })
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeyDown);
});
</script>
<style scoped lang="scss">
.tool-left {
  position: fixed;
  top: 1rem;
  left: 1rem;
}

.menu {
  position: fixed;
  margin: 0.75rem;
  padding: 1rem;
  max-width: 85%;
  max-height: 80%;
  background-color: #EBEDFF;
  border-radius: 1rem;
  box-shadow: 0 0 1rem rgba(0, 0, 0, 0.1);
  box-sizing: border-box;
}

@keyframes moveRight { /* 定义一个名为 moveRight 的动画关键帧 */
  from { /* 动画的起始状态 */
    right: -21rem;
  }
  to { /* 动画的结束状态 */
    right: 1rem;
  }
}

@keyframes moveLeft { /* 定义一个名为 moveRight 的动画关键帧 */
  from { /* 动画的起始状态 */
    right: 1rem;
  }
  to { /* 动画的结束状态 */
    right: -21rem;
  }
}

.open-animate {
  animation: moveRight 0.5s ease forwards;
}


.close-animate {
  animation: moveLeft 0.5s ease forwards;
}


.tool-right {
  position: fixed;
  right: -21rem;
  top: 50%;
  transform: translateY(-50%);
  width: 20rem;
  margin-left: -21rem;
  height: 80%;
  border-radius: 1rem;
  background-color: #ffffff;
  box-shadow: 0 0 1rem rgba(0, 0, 0, 0.1);

  .close-btn {
    position: fixed;
    top: -0.75rem;
    right: -0.75rem;
  }

  .tool-right-content {
    padding: 2rem 1rem 1rem 1rem;
    height: 100%;

    .tool-right-content-scroll {
      height: calc(100% - 6.5rem);
      overflow-y: auto;

      &::-webkit-scrollbar {
        width: 0.5rem;
      }
    }
  }

  .tool-right-footer {
    position: fixed;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
  }

  .t-form-button {
    display: flex;
    justify-content: center;
    margin-top: 1.5rem;
  }

  .t-form-location {
    position: relative;

    .t-form-close {
      position: absolute;
      z-index: 1000;
      right: 0.5rem;
      top: -0.5rem
    }
  }
}

.tool-top {
  position: fixed;
  top: 1rem;
  right: 50%;
  transform: translateX(50%);
  box-shadow: 0 0 1rem rgba(0, 0, 0, 0.1);
  background-color: #fff;
  display: flex;
  justify-content: space-around;
  align-items: center;
  padding: 1rem;
  border-radius: 1rem;

}

</style>
