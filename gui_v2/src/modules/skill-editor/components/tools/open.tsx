import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Button } from '@douyinfe/semi-ui';

export function Open(props: { disabled: boolean }) {
  const clientContext = useClientContext();

  const handleFileChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const jsonData = JSON.parse(content);
        
        // Clear current document and load new data
        clientContext.document.clear();
        clientContext.document.fromJSON(jsonData);
      } catch (error) {
        console.error('Error loading file:', error);
        // You might want to show an error message to the user here
      }
    };
    reader.readAsText(file);
  }, [clientContext]);

  return (
    <>
      <input
        type="file"
        accept=".json"
        style={{ display: 'none' }}
        onChange={handleFileChange}
        id="open-file-input"
      />
      <Button
        disabled={props.disabled}
        onClick={() => document.getElementById('open-file-input')?.click()}
        style={{ backgroundColor: 'rgba(171,181,255,0.3)', borderRadius: '8px' }}
      >
        Open
      </Button>
    </>
  );
} 