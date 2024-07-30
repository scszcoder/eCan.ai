import {nextTick, reactive, ref} from "vue";
import {fabric} from "fabric";
import {IEvent} from "fabric/fabric-impl";
import {v4 as uuidv4} from "uuid";
import {FormInstanceFunctions, FormProps, LoadingPlugin, MessagePlugin} from "tdesign-vue-next";
import {cloudAnalyzeRandomImage, getImage} from "@/api/canvas";
import _ from "lodash";

export const loading = ref(false)
export const canvas = ref<fabric.Canvas>() // 画板对象
export const currentRect = ref<fabric.Rect>() // 当前正在绘制的矩形
export const downPoint = ref() // 按下鼠标的点
export const upPoint = ref() // 抬起鼠标的点
export const currentType = ref('select'); // 当前操作类型
export const calcPoint = ref<{ x: number, y: number }>({x: 0, y: 0}) // 画布的偏移量
export const currentCalcPoint = ref<{ x: number, y: number }>({x: 0, y: 0}) // 当前画布的偏移量
export const selectionObject = ref<fabric.Object[]>() // 选中的对象
export const showReightTool = ref<number>(-1) // 0 不显示 1 显示 -1 不显示
export const zoom = ref(1)
export const imageIndex = ref(0)
export const currentRelationAnchorIndex = ref()
export const playBackData = ref<{ index: number, data: fabric.Rect[] }[]>([])
export const form = ref<FormInstanceFunctions>();
export const showDeleteDialog = ref(false)
export const canvasConfig = ref<{ width: number, height: number }>({
    width: 1920,
    height: 1080
})
export const image = [
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/click_step9_1720487811.293888.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step1_1720487801.533372.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step2_1720487804.702529.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step3_1720487805.009381.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step4_1720487805.328047.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step5_1720487805.640235.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step6_1720487805.949762.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step7_1720487806.251725.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step8_1720487806.562766.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step10_1720487811.613676.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step11_1720487812.089354.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/scroll_step12_1720487818.416766.png",
    "/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/scroll_step13_1720487818.725018.png",
]
export const formData: FormProps['data'] = reactive({
    anchor: '',
    type: '',
    template: '',
    method: '',
    location: [],
    uuid: ''
});

export const initCanvas = async () => {
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

export const init = async () => {
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
    await changeImage(0)
    document.addEventListener('keydown', handleKeyDown);
}
export const initEvent = () => {
    // 鼠标点击时事件
    canvas.value?.on('mouse:down', canvasMouseDown)
    // 鼠标移动时事件
    canvas.value?.on('mouse:move', canvasMouseMove)
    // 鼠标抬起时事件
    canvas.value?.on('mouse:up', canvasMouseUp)
    // 鼠标双击时事件
    canvas.value?.on('mouse:dblclick', canvasMouseDblclick)
    // 鼠标滚轮事件
    // canvas.value?.on('mouse:wheel', canvasMouseWheel)
    // 鼠标选中时事件
    canvas.value?.on('selection:created', canvasSelectionCreated)
    // 鼠标选中时事件
    canvas.value?.on('selection:updated', canvasSelectionUpdated)
    // 删除对象时事件
    canvas.value?.on('object:removed', (e) => {
        canvas.value?.discardActiveObject().renderAll();
    });
    // 图层移动事件
    canvas.value?.on("object:moving", canvasObjectMoving)
    // 删除所有图层事件
    canvas.value?.on('selection:cleared', canvasSelectionCleared)
}

/**
 * 让相关的文本框跟随矩形移动
 * @param e 事件对象
 */
const canvasObjectMoving = (e: fabric.IEvent<MouseEvent>) => {
    const movingObject = e.target;
    if (movingObject instanceof fabric.Rect) {
        const textBox = findTextBoxByRect(movingObject);
        textBox.forEach((obj: fabric.Textbox) => {
            obj.set({
                // @ts-ignore
                ...textBoxCalc(movingObject, obj.get('type'))
            })
        })
    }
}

const textBoxCalc = (rect: fabric.Rect, type: string = 'anchor') => {
    if (type === 'anchor') {
        return {
            left: rect.left + 5,
            top: rect.top + rect.height / 2 - 10,
        }
    }
}

const findTextBoxByRect = (rect: fabric.Rect): fabric.Textbox[] => {
    const all = findObject(fabric.Textbox)
    const textBox: fabric.Textbox[] = []
    all.forEach((obj: fabric.Textbox) => {
        // @ts-ignore
        if (obj.get('uuid') === rect.get('uuid')) {
            textBox.push(obj)
        }
    })
    return textBox;
}

const canvasMouseDblclick = (e: fabric.IEvent<MouseEvent>) => {
    downPoint.value = e.pointer
    const all = findObject(fabric.Rect)
    all.forEach((obj: fabric.Rect) => {
        if (isPointInRect(obj)) {
            canvas.value?.setActiveObject(obj);
            canvas.value?.renderAll();
        }
    })
}
/**
 * 鼠标滚轮缩放
 * @param e
 */
const canvasMouseWheel = (e: fabric.IEvent<WheelEvent>) => {
    const delta = e.e.deltaY;
    zoom.value = canvas.value?.getZoom();
    zoom.value *= 1 + 0.01 * (delta > 0 ? -1 : 1);
    if (zoom.value > 0.1 && zoom.value < 5) {
        canvas.value?.zoomToPoint({x: e.e.offsetX, y: e.e.offsetY}, zoom.value);
    }
    e.e.preventDefault();
}
/**
 * 清除选中
 * @param e
 */
const canvasSelectionCleared = (e: fabric.IEvent<MouseEvent>) => {
    selectionObject.value = undefined
    formReset()
    closeTool()
}
/**
 * 选中更新
 * @param e
 */
const canvasSelectionUpdated = (e: fabric.IEvent<MouseEvent>) => {
    const all = findObject(fabric.Rect)
    console.log('canvasSelectionUpdated', e, all)
    if (e.selected?.length === 1) {
        formReset()
        updateFormData(e)
    }
}
/**
 * 选中创建
 * @param e
 */
const canvasSelectionCreated = (e: fabric.IEvent<MouseEvent>) => {
    const all = findObject(fabric.Rect)
    console.log('canvasSelectionCreated', e, all)
    if (e.selected?.length === 1) {
        form.value?.reset()
        updateFormData(e)
    }
}

/**
 * 更新表单数据
 * @param e
 */
const updateFormData = (e: fabric.IEvent<MouseEvent>) => {
    selectionObject.value = e.selected
    showReightTool.value = 1
    // @ts-ignore
    const data = selectionObject.value![0].get('formData')
    if (data) {
        formData.anchor = data.anchor
        formData.type = data.type
        formData.template = data.template
        formData.method = data.method
        formData.location = data.location
    }
}

const canvasMouseDown = (e: IEvent<MouseEvent>) => {
    downPoint.value = e.pointer
    if (currentType.value === 'rect') {
        currentRect.value = createRect(downPoint.value.x, downPoint.value.y, 0, 0)
        canvas.value?.add(currentRect.value)
    } else if (currentType.value === 'drag') {
        canvas.value?.calcOffset();
    } else if (currentType.value === 'select') {
        const all = findObject(fabric.Rect)
        all.forEach((obj: fabric.Rect) => {
            if (isPointInRect(obj)) {
                console.log(obj)
                canvas.value?.setActiveObject(obj);
                canvas.value?.renderAll();
            }
        })
    }
}
// 判断点是否在矩形内的函数
export const isPointInRect = (rect: fabric.Object) => {
    return (
        downPoint.value.x >= rect.left! &&
        downPoint.value.x <= rect.left! + rect.width! &&
        downPoint.value.y >= rect.top! &&
        downPoint.value.y <= rect.top! + rect.height!
    );
}
// 辅助函数：处理矩形绘制
const handleRectDraw = (e: IEvent<MouseEvent>, zoomFactor: number) => {
    const downX = downPoint.value.x;
    const downY = downPoint.value.y;
    const pointerX = e.pointer!.x;
    const pointerY = e.pointer!.y;

    const newLeft = Math.min(downX, pointerX) - calcPoint.value.x;
    const newTop = Math.min(downY, pointerY) - calcPoint.value.y;
    const newWidth = Math.abs((downX - pointerX));
    const newHeight = Math.abs((downY - pointerY));
    currentRect.value.set({
        left: newLeft,
        top: newTop,
        width: newWidth,
        height: newHeight
    });
    canvas.value.renderAll();
}

// 辅助函数：处理拖拽
const handleDrag = (e: IEvent<MouseEvent>) => {
    const delta = new fabric.Point(e.e.movementX, e.e.movementY);
    currentCalcPoint.value = {x: e.pointer!.x - downPoint.value.x, y: e.pointer!.y - downPoint.value.y};
    canvas.value.relativePan(delta);
}

// 辅助函数：调整 calcPoint
export const adjustCalcPoint = (e: IEvent<MouseEvent>) => {
    return {
        x: currentCalcPoint.value.x + calcPoint.value.x,
        y: currentCalcPoint.value.y + calcPoint.value.y
    };
}
const canvasMouseMove = (e: IEvent<MouseEvent>) => {
    const c = canvas.value;
    if (!c) return;
    const zoomFactor = c.getZoom();
    if (currentType.value === 'rect' && downPoint.value && currentRect.value) {
        handleRectDraw(e, zoomFactor);
    } else if (currentType.value === 'drag' && downPoint.value) {
        handleDrag(e);
    }
}

const canvasMouseUp = (e: IEvent<MouseEvent>) => {
    const c = canvas.value;
    if (!c) return;
    if (currentType.value === 'drag') {
        calcPoint.value = adjustCalcPoint(e);
    }
    const all = findObject(fabric.Rect)
    all.forEach((obj: fabric.Rect) => {
        if (obj.width < 10 && obj.height < 10) {
            canvas.value?.remove(obj);
        }
    })
    canvas.value?.renderAll();
    currentRect.value = undefined;
    downPoint.value = null;
    upPoint.value = null;
}

export const findObject = (type: any) => {
    // 遍历所有对象
    const objects = canvas.value?.getObjects();
    return objects && objects.filter(obj => obj instanceof type);
}

export const openUpload = () => {
    const input = document.querySelector('input');
    input && input.click();
}

export const handleFileUpload = (e: Event) => {
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
export const closeTool = () => {
    showReightTool.value = 0
    formReset()
    canvas.value!.discardActiveObject().renderAll()
}

export const formReset = () => {
    form.value!.reset();
    formData.location = []
}
// 画布操作类型切换
export const typeChange = (opt: string) => {
    console.log(opt)
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
                MessagePlugin.warning("已存在图片，请先删除图片再上传").finally()
            }
            break;
        case 'clear':
            clearObject()
            break;
    }
    if (opt !== 'clear') {
        currentType.value = opt;
    }
}
export const clearObject = () => {
    const all = findObject(fabric.Rect)
    all.forEach(obj => {
        canvas.value?.remove(obj)
    })
}

const deleteObject = () => {
    if (selectionObject.value) {
        selectionObject.value.forEach(obj => {
            canvas.value?.remove(obj)
        })
    }
}


export const addRectLabel = (obj: fabric.Object, text: string, color: string = 'red') => {
    const type = 'anchor'
    const textBox = new fabric.Textbox(text, {
        // @ts-ignore
        ...textBoxCalc(obj, type),
        fontSize: 16,
        fill: color,
        selectable: false,
        evented: false,
        width: 100,
        height: 100,
        fontWeight: 'normal',
        fontStyle: 'normal',
        lineHeight: 1.2,
        textAlign: 'left',
        underline: false,
        overline: false,
        linethrough: false,
        strokeWidth: 1,
        strokeDashArray: null,
        // @ts-ignore
        uuid: obj.get('uuid'),
        type
    });
    canvas.value?.add(textBox);
    canvas.value?.renderAll();
}

const createRect = (left: number, top: number, right: number, bottom: number, color: string = 'red', formData?: any) => {
    const newWidth = right == 0 ? 0 : Math.abs((left - right));
    const newHeight = bottom == 0 ? 0 : Math.abs((top - bottom));
    const rect = new fabric.Rect({
        left: left,
        top: top,
        width: newWidth,
        height: newHeight,
        fill: 'transparent',
        stroke: color,
        lockRotation: true, // 禁止旋转
        strokeUniform: true, // 矩形尺寸变化线条大小不变
        strokeWidth: 2, // 矩形边框宽度
        // @ts-ignore
        uuid: uuidv4(),
        // @ts-ignore
        formData: formData
    })
    canvas.value?.add(rect)
    return rect
}

const addFormData = (rect: fabric.Rect, data: any) => {
    let method = '0'
    if (data.type == 'info') {
        method = '0'
    } else if (data.type == 'polygan') {
        method = '1'
    } else if (data.type == 'h line') {
        method = '2'
    }
    const formData = {
        anchor: data.text,
        type: 'text',
        template: data.text,
        method: method,
        location: [],
    }
    console.log(formData)
    // @ts-ignore
    rect.set('formData', formData)
}

const changeImage = async (index: number) => {
    const all = findObject(fabric.Rect)
    loading.value = true
    LoadingPlugin(true);
    if (all) {
        playBackData.value[imageIndex.value] = {
            index: imageIndex.value,
            data: all
        }
        all.forEach(obj => {
            canvas.value?.remove(obj)
        })
        canvas.value?.renderAll();
    }
    imageIndex.value = imageIndex.value + index
    const path = image[imageIndex.value]
    const data = await getImage({file: path})
    const cloud_data = await cloudAnalyzeRandomImage({file: path})
    const data_message = cloud_data.data

    fabric.Image.fromURL(data, (img) => {
        img.scaleToWidth(img.width!); // 保持图片原始宽度
        img.scaleToHeight(img.height!); // 保持图片原始高度
        // 禁止图片拖动
        img.set({
            selectable: false,
            evented: false,
        });
        canvas.value?.add(img);
        canvas.value?.renderAll();
        const playBack = playBackData.value[imageIndex.value]
        if (playBack) {
            playBack.data.forEach(obj => {
                canvas.value?.add(obj)
            })
            canvas.value?.renderAll();
        }

        data_message.forEach((item: any) => {
            if (item.type === 'info') {
                const rect = createRect(item.loc[1], item.loc[0], item.loc[3], item.loc[2], '#ff2fa9')
                addFormData(rect, item)
                if (item.type === 'info') {
                    const txtStruct = item.txt_struct
                    if (txtStruct) {
                        txtStruct.forEach((item1) => {
                            const rect = createRect(item1.box[0], item1.box[1], item1.box[2], item1.box[3], '#35b5ff')
                            addFormData(rect, item1)
                            const words = item1.words
                            if (words) {
                                words.forEach((item2) => {
                                    const rect = createRect(item2.box[0], item2.box[1], item2.box[2], item2.box[3], '#00ff3f')
                                    addFormData(rect, item2)
                                    addRectLabel(rect, item2.text, '#00ff3f')
                                })
                            } else {
                                addRectLabel(rect, item1.text, '#35b5ff')
                            }
                        })
                    }
                } else {
                    addRectLabel(rect, item.text, '#ff2fa9')
                }
            }
        })
    });
    LoadingPlugin(false);
}

export const handleKeyDown = async (e: KeyboardEvent) => {
    if (e.key === 'Backspace') {
        deleteObject()
    } else if (e.key === 'ArrowRight' && imageIndex.value < image.length - 1) {
        await next()
    } else if (e.key === 'ArrowLeft' && imageIndex.value > 0) {
        await last()
    }
}
export const next = async () => {
    await changeImage(1)
}

export const last = async () => {
    await changeImage(-1)
}
export const save = () => {
    const allData: any = []
    const allRect = findObject(fabric.Rect)
    allRect.forEach((rect: fabric.Rect) => {
        //@ts-ignore
        let data = rect.get('formData')
        if (!data) {
            data = {}
        } else {
            data = _.cloneDeep(data)
        }
        //@ts-ignore
        data.uuid = rect.get('uuid')
        data.left = rect.left
        data.top = rect.top
        data.width = rect.width
        data.height = rect.height
        data.stroke = rect.stroke
        allData.push(data)
    })
}
export const handleOpenDialog = (index: number) => {
    currentRelationAnchorIndex.value = index
    showDeleteDialog.value = true
}
export const handleClose = () => {
    formData.location.splice(currentRelationAnchorIndex.value, 1)
    showDeleteDialog.value = false
}
export const handleMouseEnter = (index: number) => {
    formData.location[index].showClose = true
}
export const handleMouseLeave = (index: number) => {
    formData.location[index].showClose = false
}
