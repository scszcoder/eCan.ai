export const editorStyles = {
  container: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 1000,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    boxSizing: 'border-box'
  },
  content: {
    width: '100%',
    height: '100%',
    backgroundColor: 'var(--semi-color-bg-1)',
    borderRadius: '8px',
    boxShadow: 'var(--semi-shadow-elevated)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden'
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 24px',
    borderBottom: '1px solid var(--semi-color-border)'
  },
  title: {
    fontSize: '16px',
    fontWeight: 600,
    color: 'var(--semi-color-text-0)'
  },
  closeButton: {
    cursor: 'pointer',
    fontSize: '20px',
    lineHeight: 1,
    color: 'var(--semi-color-text-2)'
  },
  editorContainer: {
    flex: 1,
    overflow: 'hidden',
    padding: '0 24px'
  },
  footer: {
    display: 'flex',
    justifyContent: 'flex-end',
    padding: '16px 24px',
    borderTop: '1px solid var(--semi-color-border)'
  },
  button: {
    padding: '6px 16px',
    borderRadius: '3px',
    cursor: 'pointer',
    fontSize: '14px',
    lineHeight: '20px'
  },
  cancelButton: {
    marginRight: '8px',
    border: '1px solid var(--semi-color-border)',
    backgroundColor: 'var(--semi-color-bg-2)',
    color: 'var(--semi-color-text-0)'
  },
  okButton: {
    border: 'none',
    backgroundColor: 'var(--semi-color-primary)',
    color: 'white'
  }
} as const; 