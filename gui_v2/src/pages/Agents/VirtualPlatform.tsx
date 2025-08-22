import React, { useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import departments from './data/departments';
import Door from './components/Door';
import './VirtualPlatform.css';
import { useTranslation } from 'react-i18next';

function getGridTemplate(deptCount: number) {
  // 2~4个门：2列，5~6个：3列，7~9个：3列，10+：4列
  if (deptCount <= 4) return 'repeat(2, 1fr)';
  if (deptCount <= 6) return 'repeat(3, 1fr)';
  if (deptCount <= 9) return 'repeat(3, 1fr)';
  return 'repeat(4, 1fr)';
}

const satelliteDots = [
  {cx: 180, cy: 120, r: 6}, {cx: 320, cy: 90, r: 4}, {cx: 1050, cy: 180, r: 7},
  {cx: 900, cy: 120, r: 5}, {cx: 200, cy: 700, r: 5}, {cx: 1100, cy: 600, r: 6},
  {cx: 1000, cy: 400, r: 4}, {cx: 800, cy: 720, r: 5}, {cx: 400, cy: 720, r: 4},
  {cx: 600, cy: 100, r: 7}, {cx: 100, cy: 400, r: 5}, {cx: 1150, cy: 350, r: 4}
];

const VirtualPlatform: React.FC = () => {
  const deptCount = departments.length;
  // 使用 useMemo 缓存计算结果，避免每次渲染重新计算
  const gridTemplate = useMemo(() => getGridTemplate(deptCount), [deptCount]);
  const navigate = useNavigate();
  const { t } = useTranslation();

  // 使用 useCallback 缓存导航函数，避免每次渲染创建新函数
  const handleDoorClick = useCallback((deptId: string) => {
    navigate(`/agents/room/${deptId}`); // Navigate to nested route
  }, [navigate]);

  // 使用 useMemo 缓存门组件的渲染，避免每次重新创建
  const doorComponents = useMemo(() => {
    return departments.map((dept) => (
      <div key={dept.id} onClick={() => handleDoorClick(dept.id)} style={{cursor: 'pointer'}}>
        <Door name={t(dept.name)} />
      </div>
    ));
  }, [departments, handleDoorClick, t]);

  return (
    <div className="virtual-platform">
      {/* SVG虚拟地板和网格 */}
      <svg className="virtual-bg-svg" width="100%" height="100%" viewBox="0 0 1200 800" style={{position:'absolute',left:0,top:0,zIndex:0}}>
        {/* 椭圆地板 */}
        <ellipse cx="600" cy="700" rx="420" ry="80" fill="var(--ant-primary-1, #e6f4ff)" opacity="0.7" />
        {/* 网格线条 */}
        {Array.from({length: 7}).map((_,i) => (
          <ellipse key={i} cx="600" cy="700" rx={180+i*40} ry={34+i*8} fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="1.5" opacity="0.18" />
        ))}
        {/* 径向发光线 */}
        {Array.from({length: 12}).map((_,i) => {
          const angle = (2*Math.PI*i)/12;
          return <line key={i} x1={600} y1={700} x2={600+420*Math.cos(angle)} y2={700+80*Math.sin(angle)} stroke="var(--ant-primary-2, #91caff)" strokeWidth="1.2" opacity="0.10" />
        })}
        {/* 智能节点 */}
        {[{cx:300,cy:200},{cx:900,cy:250},{cx:600,cy:400},{cx:400,cy:600},{cx:800,cy:650}].map((n,i)=>(
          <circle key={i} cx={n.cx} cy={n.cy} r="18" fill="var(--ant-primary-color, #1677ff)" opacity="0.18" filter="url(#glow)" />
        ))}
        {/* 卫星点 */}
        {satelliteDots.map((dot, i) => (
          <circle key={"sat"+i} cx={dot.cx} cy={dot.cy} r={dot.r} fill="var(--ant-primary-color, #1677ff)" opacity="0.32" filter="url(#glow)" />
        ))}
        {/* 数据流/流程线 */}
        <polyline points="300,200 600,400 900,250" fill="none" stroke="var(--ant-primary-color, #1677ff)" strokeWidth="3" opacity="0.13" />
        <polyline points="400,600 600,400 800,650" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="2" opacity="0.10" />
        {/* AI脑波/光圈 */}
        <ellipse cx="600" cy="400" rx="80" ry="30" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="2" opacity="0.10" />
        {/* SVG滤镜：发光 */}
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="8" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
      </svg>
      {/* 光斑/灯光 */}
      <div className="virtual-bg-blur virtual-bg-blur1" />
      <div className="virtual-bg-blur virtual-bg-blur2" />
      {/* 门规则网格分布 */}
      <div className="doors-grid" style={{gridTemplateColumns: gridTemplate}}>
        {doorComponents}
      </div>
    </div>
  );
};

export default React.memo(VirtualPlatform); 