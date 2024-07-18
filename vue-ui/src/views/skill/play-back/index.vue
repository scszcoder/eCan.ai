<template>
  <div class="drawing-board">
    <el-row type="flex" style="margin-bottom: 50px">
      <input id="setColor" v-model="brushColor" @change="selectColor" type="color" style="opacity: 0" />
      <el-button :icon="EditPen" circle size="small" @click="openColorSelect"></el-button>
      <el-button :type="paintBrush ? 'primary' : 'default'" @click="openRangeInput">设置画笔粗细</el-button>
      <el-button type="primary" @click.stop="selectEraser(fabricStatus)">{{ fabricStatus ? '使用画笔' : '使用橡皮擦' }}</el-button>
      <el-button :type="paintEraser ? 'primary' : 'default'" @click="openBrushNum">设置橡皮擦粗细</el-button>
      <el-button type="primary" @click="undo()">上一步</el-button>
      <el-button type="primary" @click="redo()">下一步</el-button>
    </el-row>
    <canvas ref="canvasRef" id="canvas" :width="clientWidth" :height="clientHeight"></canvas>
  </div>
</template>

<script setup>
// 导入fabric第三方库
import { fabric } from 'fabric-with-erasing';
import { onMounted, ref, nextTick } from 'vue';
import { EditPen } from '@element-plus/icons-vue'

const clientWidth = ref()
const clientHeight = ref()
// 创建canvas实例
const canvasRef = ref();

// 画板中默认显示的图片路径
const showImgSrc = '/Users/tangyu/Projects/Tanyo/ecbot/ecbot/resource/skills/temp/20240709-091641/move_step2_1720487804.702529.png';

// 画笔颜色
const brushColor = ref('#000');

// 画笔粗细滑块显示/隐藏
const paintBrush = ref(false);

// 画笔粗细
const brushNum = ref(10);

// eraser粗细滑块显示/隐藏
const paintEraser = ref(false);

// 橡皮擦粗细
const eraser = ref(10);

// 当前状态为画笔/橡皮差
const fabricStatus = ref(false);

// 撤销的快照数组,用来记录历史
let undoList = [];

// 恢复的快照数组,用来记录历史
let redoList = [];

// 添加新状态到历史记录中
function saveState() {
  undoList.push(JSON.stringify(canvasRef.value.toDatalessJSON()));
}

// 撤销操作
function undo() {
  // 点击撤销按钮时将undoList中的最后一个画面移动到redoList中
  if (undoList.length !== 0) {
    const last = undoList.pop();
    redoList.push(last);
    // 调用绘画页面的方法
    // canvasRef.value.loadFromJSON(last, function () {
    //   canvasRef.value.renderAll();
    // });
  }
}

// 恢复操作
function redo() {
  // 点击撤销按钮时将undoList中的最后一个画面移动到redoList中
  if (redoList.length !== 0) {
    undoList.push(redoList.pop());
    // 调用绘画页面的方法
    canvasRef.value.loadFromJSON(redoList[redoList.length - 1], function () {
      canvasRef.value.renderAll();
    });
  }
}

// 将图片绘制到canvas中
const drawCanvas = () => {
  // 获取canvas元素,fabric将功能应用到此canvas中
  const canvas = document.querySelector('#canvas');

  // 创建一个img实例
  const img = new Image();

  // 设置img的图片地址,后续此图片将会加载进canvas中
  img.src = showImgSrc;

  // 在图片记载完成后进行处理
  img.onload = function () {
    // fabric实例化
    canvasRef.value = new fabric.Canvas(canvas, {
      // 内部图像不允许拖动(因为拖动的动作为画笔动作,两者冲突)
      selection: false,
      // 开启画笔
      isDrawingMode: true,
      // 笔刷高清
      devicePixelRatio: true,
    });

    // 创建图像图层
    let imgLayer = new fabric.Image(img, {
      erasable: false, // 不允许擦拭
      // 设置图像在fabric画板中的位置为水平垂直居中
      left: 0,
      top: 0,
      scaleX: 1,
      scaleY: 1
    });

    // 将图片添加到canvas中
    canvasRef.value.add(imgLayer);

    // 监听鼠标按下事件，添加新的状态到历史记录
    canvasRef.value.on('mouse:down', function () {
      saveState();
    });

    // 监听鼠标抬起事件，添加新的状态到历史记录
    canvasRef.value.on('mouse:up', function () {
      saveState();
    });

    // 添加缩放功能
    canvasRef.value.on('mouse:wheel', event => {
      // 获取鼠标的缩放值
      var delta = event.e.deltaY;

      // 获取当前画布的缩放值
      var zoom = canvasRef.value.getZoom();

      // 根据鼠标滚轮的滚动设置画布的缩放值
      zoom *= 0.999 ** delta;

      // 设置缩放值最大为1.5(原先图像的1.5倍)
      if (zoom > 1.5) zoom = 1.5;

      // 设置缩放值最小为0.5(原先图像的0.5倍)
      if (zoom < 0.5) zoom = 0.5;

      // 给定缩放所在的位置以及缩放的大小,画板就会根据给定的位置进行缩放
      canvasRef.value.zoomToPoint({ x: event.e.offsetX, y: event.e.offsetY }, zoom);

      // 阻止默认行为与阻止事件冒泡
      event.e.preventDefault();
      event.e.stopPropagation();
    });
  };
};

// 打开颜色选择画板
const openColorSelect = () => {
  nextTick(() => document.querySelector('#setColor').click());
};

// 修改画笔颜色
const selectColor = ({ target }) => {
  canvasRef.value.freeDrawingBrush.color = target.value;
};

// 切换橡皮擦/画笔状态
const selectEraser = status => {
  // 判断是否为画笔状态
  if (!status) {
    changeAction('erase');
    // 修改为橡皮擦状态
  } else {
    changeAction('undoErasing');
  }
  // 切换为另一个状态
  fabricStatus.value = !fabricStatus.value;
};

// 打开/关闭设置画笔粗细滑块
const openRangeInput = () => {
  paintBrush.value = !paintBrush.value;
};

// 修改画笔粗细
const changeBrushNum = () => {
  canvasRef.value.freeDrawingBrush.width = brushNum.value; // 设置画笔粗细为 10
  changeAction(fabricStatus.value ? 'erase' : 'undoErasing');
};

// 打开/关闭设置橡皮擦粗细滑块
const openBrushNum = () => {
  paintEraser.value = !paintEraser.value;
};

// 修改橡皮擦粗细
const changeEraserNum = () => {
  canvasRef.value.freeDrawingBrush.width = eraser.value; // 设置橡皮擦粗细
  changeAction(fabricStatus.value ? 'erase' : 'undoErasing');
};

// 修改画板行为模式
function changeAction(mode) {
  switch (mode) {
    case 'erase':
      canvasRef.value.freeDrawingBrush = new fabric.EraserBrush(canvasRef.value); // 使用橡皮擦
      canvasRef.value.freeDrawingBrush.width = eraser.value; // 设置橡皮擦粗细
      break;
    case 'undoErasing':
      canvasRef.value.freeDrawingBrush = new fabric.PencilBrush(canvasRef.value); // 使用橡皮擦
      canvasRef.value.freeDrawingBrush.color = brushColor.value; // 使用画笔
      canvasRef.value.freeDrawingBrush.width = brushNum.value; // 设置画笔粗细
    default:
      break;
  }
}

onMounted(() => {
  clientWidth.value = document.documentElement.clientWidth
  clientHeight.value = document.documentElement.clientHeight-32-50-20
  window.onresize = function () {
    clientWidth.value = document.documentElement.clientWidth
    clientHeight.value = document.documentElement.clientHeight-32-50-20
  };
  drawCanvas();
});
</script>

<style scoped>
#canvas {
  width: 100%;
  height: 100%;
}
.drawing-board {
  width: 100vw;
  height: 100vh;
}
</style>
