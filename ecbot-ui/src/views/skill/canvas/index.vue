<template>
  <canvas id="canvas"></canvas>

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
import {CloseIcon, Icon, MenuApplicationIcon} from "tdesign-icons-vue-next";
import {FormInstanceFunctions, FormProps, MessagePlugin} from "tdesign-vue-next";
import {useI18n} from 'vue-i18n';
import {v4 as uuidv4} from 'uuid';
import _ from 'lodash';
import {useRoute} from "vue-router";
import {IEvent} from "fabric/fabric-impl";

const {t, locale} = useI18n()
const route = useRoute();
const form = ref<FormInstanceFunctions>();
const showDeleteDialog = ref(false)
const currentRelationAnchorIndex = ref()
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

const formData: FormProps['data'] = reactive({
  anchor: '',
  type: '',
  template: '',
  method: '',
  location: [],
  uuid: ''
});

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
  {value: 'em', label: 'em'},
  {value: 'rem', label: 'rem'},
  {value: 'vw', label: 'vw'},
  {value: 'vh', label: 'vh'},
  {value: '%', label: '%'},
]
const handleOpenDialog = (index: number) => {
  currentRelationAnchorIndex.value = index
  showDeleteDialog.value = true
}
const handleClose = () => {
  formData.location.splice(currentRelationAnchorIndex.value, 1)
  showDeleteDialog.value = false
}

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

const handleMouseEnter = (index: number) => {
  formData.location[index].showClose = true
}
const handleMouseLeave = (index: number) => {
  formData.location[index].showClose = false
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
        // @ts-ignore
        selectionObject.value![0].set('formData', data)
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

const formReset = () => {
  form.value!.reset();
  formData.location = []
}

const menu = ref(true)

const openMenu = () => {
  menu.value = !menu.value
}

const options = reactive([
  {type: 'select', icon: 'gesture-up', text: '选取'},
  {type: 'drag', icon: 'drag-move', text: '拖动'},
  {type: 'rect', icon: 'rectangle', text: '矩形'},
  {type: 'file', icon: 'upload', text: '上传'},
  {type: 'delete', icon: 'delete', text: '删除'}
])

const openUpload = () => {
  const input = document.querySelector('input');
  input && input.click();
}

const handleFileUpload = (e: Event) => {
  const file = (e.target as HTMLInputElement).files![0];
  const reader = new FileReader();

  reader.onload = (evt: ProgressEvent<FileReader>) => {
    if (evt.target?.result) {
      fabric.Image.fromURL(evt.target.result as string, (img) => {
        img.scaleToWidth(img.width!); // 保持图片原始宽度
        img.scaleToHeight(img.height!); // 保持图片原始高度
        // 禁止图片拖动
        img.set({
          selectable: false,
          evented: false,
        });
        canvas.value?.add(img);
        canvas.value?.renderAll();
      });
    }
  };
  reader.readAsDataURL(file);
}
const closeTool = () => {
  showReightTool.value = 0
  formReset()
  canvas.value!.discardActiveObject().renderAll()
}
const canvasConfig = ref<{ width: number, height: number }>({
  width: 1920,
  height: 1080
})
const canvas = ref<fabric.Canvas>() // 画板对象
const currentRect = ref<fabric.Rect>() // 当前正在绘制的矩形
const downPoint = ref() // 按下鼠标的点
const upPoint = ref() // 抬起鼠标的点
const currentType = ref('select'); // 当前操作类型
const calcPoint = ref<{ x: number, y: number }>({x: 0, y: 0}) // 画布的偏移量
const currentCalcPoint = ref<{ x: number, y: number }>({x: 0, y: 0}) // 当前画布的偏移量
const selectionObject = ref<fabric.Object[]>() // 选中的对象
const allObjects = ref<fabric.Object[]>([])
const showReightTool = ref<number>(-1) // 0 不显示 1 显示 -1 不显示
const initEvent = () => {
  canvas.value?.on('mouse:down', canvasMouseDown)
  canvas.value?.on('mouse:move', canvasMouseMove)
  canvas.value?.on('mouse:up', canvasMouseUp)
  canvas.value?.on('selection:created', canvasSelectionCreated)
  canvas.value?.on('selection:updated', canvasSelectionUpdated)
  canvas.value?.on('object:removed', (e) => {
    canvas.value?.discardActiveObject().renderAll();
  });
  canvas.value?.on('selection:cleared', canvasSelectionCleared)
}
const canvasSelectionCleared = (e: fabric.IEvent<MouseEvent>) => {
  selectionObject.value = undefined
  formReset()
  closeTool()
}
const canvasSelectionUpdated = (e: fabric.IEvent<MouseEvent>) => {
  if (e.selected?.length === 1) {
    formReset()
    selectionObject.value = e.selected
    showReightTool.value = 1
    // @ts-ignore
    const data = selectionObject.value![0].get('formData')
    console.log(data)
    if (data) {
      formData.anchor = data.anchor
      formData.type = data.type
      formData.template = data.template
      formData.method = data.method
      formData.location = data.location
    }
  }
}
const canvasSelectionCreated = (e: fabric.IEvent<MouseEvent>) => {
  if (e.selected?.length === 1) {
    form.value?.reset()
    selectionObject.value = e.selected
    showReightTool.value = 1
    // @ts-ignore
    const data = selectionObject.value![0].get('formData')
    console.log(data)
    if (data) {
      formData.anchor = data.anchor
      formData.type = data.type
      formData.template = data.template
      formData.method = data.method
      formData.location = data.location
    }
  }
}

const canvasMouseDown = (e: IEvent<MouseEvent>) => {
  downPoint.value = e.pointer
  if (currentType.value === 'rect') {
    currentRect.value = new fabric.Rect({
      left: downPoint.value.x,
      top: downPoint.value.y,
      width: 0,
      height: 0,
      fill: 'transparent',
      stroke: 'red',
      lockRotation: true, // 禁止旋转
      strokeUniform: true, // 矩形尺寸变化线条大小不变
      strokeWidth: 1, // 矩形边框宽度
      // @ts-ignore
      uuid: uuidv4(),
    })
    canvas.value?.add(currentRect.value)
    allObjects.value.push(currentRect.value)
  } else if (currentType.value === 'drag') {
    canvas.value?.calcOffset();
  } else if (currentType.value === 'select') {
    allObjects.value.forEach((obj) => {
      if (isPointInRect(obj)) {
        canvas.value?.setActiveObject(obj);
        canvas.value?.renderAll();
      }
    })
  }
}
// 判断点是否在矩形内的函数
const isPointInRect = (rect: fabric.Object) => {
  return (
      downPoint.value.x >= rect.left! &&
      downPoint.value.x <= rect.left! + rect.width! &&
      downPoint.value.y >= rect.top! &&
      downPoint.value.y <= rect.top! + rect.height!
  );
}
const canvasMouseMove = (e: IEvent<MouseEvent>) => {
  if (currentType.value === 'rect' && downPoint.value && currentRect.value) {
    const newLeft = Math.min(downPoint.value.x, e.pointer!.x) - calcPoint.value.x
    const newTop = Math.min(downPoint.value.y, e.pointer!.y) - calcPoint.value.y
    const newWidth = Math.abs(downPoint.value.x - e.pointer!.x)
    const newHeight = Math.abs(downPoint.value.y - e.pointer!.y)
    currentRect.value.set({
      left: newLeft,
      top: newTop,
      width: newWidth,
      height: newHeight
    })
    canvas.value?.renderAll()
  } else if (currentType.value === 'drag' && downPoint.value) {
    const delta = new fabric.Point(e.e.movementX, e.e.movementY);
    currentCalcPoint.value = {x: e.pointer!.x - downPoint.value.x, y: e.pointer!.y - downPoint.value.y}
    canvas.value?.relativePan(delta);
  }
}

const canvasMouseUp = (e: IEvent<MouseEvent>) => {
  if (currentType.value === 'drag') {
    calcPoint.value = {x: currentCalcPoint.value.x + calcPoint.value.x, y: currentCalcPoint.value.y + calcPoint.value.y}
  }
  currentRect.value = undefined
  downPoint.value = null
  upPoint.value = null
}

// 画布操作类型切换
const typeChange = (opt: string) => {
  currentType.value = opt;
  switch (opt) {
    case 'select': // 默认框选模式
      canvas.value!.selection = true; // 允许框选
      canvas.value!.selectionColor = 'rgba(100,100,255,0.3)'; // 选框填充色:半透明的蓝色
      canvas.value!.selectionBorderColor = 'rgba(255,255,255,0.3)'; // 选框边框颜色:半透明灰色
      canvas.value!.skipTargetFind = false; // 允许选中
      break;
    case 'rect': // 创建矩形模式
      canvas.value!.selection = false; // 允许框选
      canvas.value!.selectionColor = 'transparent'; // 选框填充色:透明
      canvas.value!.selectionBorderColor = 'rgba(0,0,0,0.2)'; // 选框边框颜色:透明度很低的黑色(看上去是灰色)
      canvas.value!.skipTargetFind = true; // 禁止选中
      break;
    case 'file': // 上传文件模式
      const image = findObject(fabric.Image)
      if (image!.length == 0) {
        openUpload()
      } else {
        MessagePlugin.warning("已存在图片，请先删除图片再上传")
      }
      break;
    case 'delete':
      deleteObject()
  }
}
const deleteObject = () => {
  if (selectionObject.value) {
    selectionObject.value.forEach(obj => {
      canvas.value?.remove(obj)
    })
  }
}

const findObject = (type: any) => {
  // 遍历所有对象
  const objects = canvas.value?.getObjects();
  return objects && objects.filter(obj => obj instanceof type);
}
const initCanvas = async () => {
  await nextTick(() => {
    canvas.value = new fabric.Canvas('canvas', {
      backgroundColor: '#fff',
      selection: false,
      hoverCursor: 'default',
      isDrawingMode: false,
      preserveObjectStacking: true,
      width: canvasConfig.value.width,
      height: canvasConfig.value.height,
      freeDrawingCursor: 'default',
    })
  })
}
const handleKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'Backspace') {
    deleteObject()
  } else if (e.key === 'ArrowRight') {
    console.log('ArrowRight');
  } else if (e.key === 'ArrowLeft') {
    console.log('ArrowLeft');
  }
}
const init = async () => {
  canvasConfig.value = {
    width: document.documentElement.clientWidth,
    height: document.documentElement.clientHeight
  }
  await initCanvas()
  window.onresize = () => {
    canvasConfig.value = {
      width: document.documentElement.clientWidth,
      height: document.documentElement.clientHeight
    }
    canvas.value?.setWidth(canvasConfig.value.width)
    canvas.value?.setHeight(canvasConfig.value.height)
  }
  initEvent()
  typeChange(currentType.value)
  document.addEventListener('keydown', handleKeyDown);
}
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
    right: -26rem;
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
    right: -26rem;
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
  right: -26rem;
  top: 50%;
  transform: translateY(-50%);
  width: 25rem;
  margin-left: -26rem;
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

</style>
