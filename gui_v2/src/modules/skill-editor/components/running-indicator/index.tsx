import runningGif from '/src/assets/gifs/running0.gif';
import styles from './index.module.less';

export const RunningIndicator = () => {
  return (
    <div className={styles.runningIndicator}>
      <img src={runningGif} alt="Running..." />
    </div>
  );
};
