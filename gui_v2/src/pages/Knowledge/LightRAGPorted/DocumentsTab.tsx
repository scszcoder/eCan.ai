import { theme, Pagination, Select, Modal, App, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { ScanOutlined, UnorderedListOutlined, ClearOutlined, FolderOpenOutlined, UploadOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import React, { useState } from 'react';

interface Document {
  id: string;
  file_path: string;
  status: string;
  content_length?: number;
  chunks_count?: number;  // LightRAG API 返回 chunks_count
  content_summary?: string;  // LightRAG API 返回 content_summary
  created_at?: string;
  updated_at?: string;
}

// 目录扫描结果类型
interface DirScanResult {
  path: string;
  files: string[];
  loading: boolean;
}

// 根据文件扩展名返回对应图标
const getFileIcon = (filename: string): string => {
  const ext = filename.toLowerCase().split('.').pop() || '';
  
  // PDF
  if (ext === 'pdf') return '📕';
  
  // Word 文档
  if (['doc', 'docx', 'odt', 'rtf'].includes(ext)) return '📘';
  
  // Excel 表格
  if (['xls', 'xlsx', 'csv', 'tsv'].includes(ext)) return '📗';
  
  // PowerPoint
  if (['ppt', 'pptx'].includes(ext)) return '📙';
  
  // 文本/Markdown
  if (['txt', 'md', 'rst', 'log'].includes(ext)) return '📝';
  
  // 代码文件
  if (['py', 'js', 'ts', 'tsx', 'jsx', 'java', 'c', 'cpp', 'go', 'rb', 'php', 'swift', 'sql', 'sh', 'bat'].includes(ext)) return '💻';
  
  // 网页
  if (['html', 'htm', 'css', 'scss', 'less'].includes(ext)) return '🌐';
  
  // 配置/数据文件
  if (['json', 'xml', 'yaml', 'yml', 'ini', 'conf', 'properties'].includes(ext)) return '⚙️';
  
  // 图片
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp', 'tif', 'tiff'].includes(ext)) return '🖼️';
  
  // 视频
  if (['mp4', 'mov', 'm4v', 'avi', 'mkv', 'webm', 'flv', 'wmv', 'mpg', 'mpeg'].includes(ext)) return '🎬';
  
  // 电子书
  if (['epub', 'tex'].includes(ext)) return '📚';
  
  // 默认文档图标
  return '📄';
};

const DocumentsTab: React.FC = () => {
  const { message } = App.useApp();
  const [modal, contextHolder] = Modal.useModal();
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [selectedDirs, setSelectedDirs] = useState<DirScanResult[]>([]);
  const [log, setLog] = useState<string>('');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [statusCounts, setStatusCounts] = useState({ all: 0, PROCESSED: 0, PROCESSING: 0, PENDING: 0, FAILED: 0 });
  const [loading, setLoading] = useState(false);
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalDocs, setTotalDocs] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const appendLog = (line: string) => setLog(prev => prev ? prev + '\n' + line : line);

  // Load documents on mount
  React.useEffect(() => {
    loadDocuments();
    loadStatusCounts();
  }, [currentPage, pageSize, statusFilter]);

  const handleSelectFiles = async () => {
    try {
      // 5 minutes timeout for user interaction
      const response = await get_ipc_api().executeRequest<any>('fs.selectFiles', { multiple: true }, 300000);
      if (response.success && response.data) {
          const result = response.data;
          if (result && result.paths && result.paths.length > 0) {
            // 追加新文件到现有列表，避免重复
            setSelectedFiles(prev => {
              const newPaths = result.paths.filter((p: string) => !prev.includes(p));
              return [...prev, ...newPaths];
            });
            appendLog(t('pages.knowledge.documents.selectFilesWithCount', { count: result.paths.length }));
          }
      }
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.errorSelectingFiles') + (e?.message || String(e)));
    }
  };

  const handleSelectDirectory = async () => {
    try {
      // 5 minutes timeout for user interaction
      const response = await get_ipc_api().executeRequest<any>('fs.selectDirectory', {}, 300000);
      if (response.success && response.data) {
          const result = response.data;
          if (result && result.path) {
            const dirPath = result.path;
            // 检查是否已存在
            if (selectedDirs.some(d => d.path === dirPath)) {
              appendLog(t('pages.knowledge.documents.directoryAlreadySelected', { path: dirPath }));
              return;
            }
            
            // 先添加目录，标记为加载中
            setSelectedDirs(prev => [...prev, { path: dirPath, files: [], loading: true }]);
            appendLog(t('pages.knowledge.documents.scanningDirectory', { path: dirPath }));
            
            // 扫描目录获取文件列表
            const scanResponse = await get_ipc_api().lightragApi.scanDirectory({ dirPath });
            if (scanResponse.success && scanResponse.data) {
              const scanData = scanResponse.data as any;
              const files = scanData.files || [];
              const skippedCount = scanData.skipped_count || 0;
              
              // 更新目录的文件列表
              setSelectedDirs(prev => prev.map(d => 
                d.path === dirPath ? { ...d, files, loading: false } : d
              ));
              
              appendLog(t('pages.knowledge.documents.directoryScanComplete', { 
                path: dirPath, 
                count: files.length,
                skipped: skippedCount
              }));
            } else {
              // 扫描失败，移除目录
              setSelectedDirs(prev => prev.filter(d => d.path !== dirPath));
              appendLog(t('pages.knowledge.documents.errorScanningDirectory') + (scanResponse.error?.message || 'Unknown error'));
            }
          }
      }
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.errorSelectingDirectory') + (e?.message || String(e)));
    }
  };

  // 导入文件
  const handleIngestFiles = async () => {
    if (!selectedFiles || selectedFiles.length === 0) {
      appendLog(t('pages.knowledge.documents.noFilesSelected'));
      return;
    }
    try {
      appendLog(`Ingesting ${selectedFiles.length} file(s)...`);
      const response = await get_ipc_api().lightragApi.ingestFiles({ paths: selectedFiles });
      if (response.success && response.data) {
        const res = response.data as any;
        appendLog(t('pages.knowledge.documents.ingestSuccess') + ': ' + JSON.stringify(res));
        setSelectedFiles([]);
        // Reload documents after ingestion
        setTimeout(() => {
          loadDocuments();
          loadStatusCounts();
        }, 2000);
      } else {
        throw new Error(response.error?.message || 'Unknown error');
      }
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.ingestError') + ': ' + (e?.message || String(e)));
    }
  };

  // 导入目录（直接导入扫描出的文件）
  const handleIngestDirs = async () => {
    if (!selectedDirs || selectedDirs.length === 0) {
      appendLog(t('pages.knowledge.documents.noDirectorySelected'));
      return;
    }
    try {
      // 收集所有目录中的文件
      const allFiles: string[] = [];
      for (const dir of selectedDirs) {
        if (dir.files && dir.files.length > 0) {
          allFiles.push(...dir.files);
        }
      }
      
      if (allFiles.length === 0) {
        appendLog(t('pages.knowledge.documents.noFilesInDirectories'));
        return;
      }
      
      appendLog(`Ingesting ${allFiles.length} file(s) from ${selectedDirs.length} directory(ies)...`);
      const response = await get_ipc_api().lightragApi.ingestFiles({ paths: allFiles });
      if (response.success && response.data) {
        const res = response.data as any;
        appendLog(t('pages.knowledge.documents.ingestSuccess') + ': ' + JSON.stringify(res));
      } else {
        throw new Error(response.error?.message || 'Unknown error');
      }
      
      setSelectedDirs([]);
      // Reload documents after ingestion
      setTimeout(() => {
        loadDocuments();
        loadStatusCounts();
      }, 2000);
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.ingestError') + ': ' + (e?.message || String(e)));
    }
  };

  const handleRemoveFile = (path: string) => {
    setSelectedFiles(prev => prev.filter(p => p !== path));
  };

  const handleRemoveDir = (dirPath: string) => {
    setSelectedDirs(prev => prev.filter(d => d.path !== dirPath));
  };

  const handleClearFiles = () => {
    setSelectedFiles([]);
  };

  const handleClearDirs = () => {
    setSelectedDirs([]);
  };


  const loadStatusCounts = async () => {
    try {
      const response = await get_ipc_api().lightragApi.getStatusCounts();
      if (response.success && response.data) {
          const res = response.data as any;
          // 支持两种数据结构：res.status_counts 或 res.data.status_counts
          const counts = res?.status_counts || res?.data?.status_counts;
          
          if (counts) {
            // Normalize keys to uppercase to handle potential case mismatch (e.g. 'failed' vs 'FAILED')
            const normalizedCounts: Record<string, number> = {};
            Object.keys(counts).forEach(key => {
              normalizedCounts[key.toUpperCase()] = counts[key];
            });

            // Calculate total
            let all = 0;
            Object.values(counts).forEach((c: any) => all += (c || 0));
            
            setStatusCounts({
              all,
              PROCESSED: normalizedCounts.PROCESSED || 0,
              PROCESSING: normalizedCounts.PROCESSING || 0,
              PENDING: normalizedCounts.PENDING || 0,
              FAILED: normalizedCounts.FAILED || 0
            });
          }
      }
    } catch (e) {
      console.error('Error loading status counts:', e);
    }
  };

  const loadDocuments = async () => {
    try {
      setLoading(true);
      
      // Use paginated API
      const response = await get_ipc_api().lightragApi.getDocumentsPaginated({
        page: currentPage,
        page_size: pageSize,
        status_filter: statusFilter === 'ALL' ? null : statusFilter,
        sort_field: 'updated_at',
        sort_direction: 'desc'
      });

      if (response.success && response.data) {
          const res = response.data as any;
          // 支持两种数据结构：res.documents 或 res.data.documents
          const docsArray = res?.documents || res?.data?.documents;
          const pagination = res?.pagination || res?.data?.pagination;
          const statusCountsData = res?.status_counts || res?.data?.status_counts;
          
          console.log('[DocumentsTab] loadDocuments response:', { res, docsArray, pagination, statusCountsData });
          
          // 更新 status counts（如果返回了）
          if (statusCountsData) {
            const normalizedCounts: Record<string, number> = {};
            Object.keys(statusCountsData).forEach(key => {
              normalizedCounts[key.toUpperCase()] = statusCountsData[key];
            });
            // 计算所有状态的文档总数（包括 PREPROCESSED 等）
            const all = Object.values(statusCountsData).reduce((sum: number, c: any) => sum + (c || 0), 0);
            // 只有当 statusFilter 为 ALL 时才更新 all，否则保持原值
            setStatusCounts(prev => ({
              all: statusFilter === 'ALL' ? all : prev.all || all,
              PROCESSED: normalizedCounts.PROCESSED || 0,
              PROCESSING: normalizedCounts.PROCESSING || 0,
              PENDING: normalizedCounts.PENDING || 0,
              FAILED: normalizedCounts.FAILED || 0
            }));
          }
          
          if (Array.isArray(docsArray)) {
            setDocuments(docsArray);
            setTotalDocs(pagination?.total_count || docsArray.length);
            if (docsArray.length > 0) {
              appendLog(t('pages.knowledge.documents.loadedDocuments', { count: docsArray.length, page: currentPage }));
            }
          } else if (res && res.data && res.data.statuses) {
            // Fallback for older API or if pagination not supported fully
            // Flatten all documents from different statuses
            const allDocs: Document[] = [];
            Object.keys(res.data.statuses).forEach((status: string) => {
              if (statusFilter && statusFilter !== 'ALL' && status !== statusFilter) return;
              const docs = res.data.statuses[status] || [];
              docs.forEach((doc: any) => {
                allDocs.push({ ...doc, status });
              });
            });
            
            // Manual pagination if backend returns all
            const start = (currentPage - 1) * pageSize;
            const end = start + pageSize;
            setDocuments(allDocs.slice(start, end));
            setTotalDocs(allDocs.length);
          }
      } else {
          appendLog('Error loading documents: ' + (response.error?.message || 'Unknown error'));
      }
    } catch (e: any) {
      appendLog('Error loading documents: ' + (e?.message || String(e)));
    } finally {
      setLoading(false);
    }
  };

  const handleScan = async () => {
    try {
      appendLog(t('pages.knowledge.documents.startingScan'));
      
      // Record current failed count before scan
      const previousFailedCount = statusCounts.FAILED;
      
      const response = await get_ipc_api().lightragApi.scan();
      if (response.success && response.data) {
          const res = response.data as any;
          appendLog(t('pages.knowledge.documents.scanStarted') + JSON.stringify(res));
          message.success(t('pages.knowledge.documents.scanStarted') + (res.message || ''));
          
          // Reload documents after scan and start polling for failures
          setTimeout(async () => {
            await loadDocuments();
            await loadStatusCounts();
            
            // Poll for failed documents - check every 3 seconds for up to 120 seconds
            let pollCount = 0;
            const maxPolls = 40; // 40 polls * 3 seconds = 120 seconds max
            let failureDetected = false;
            
            console.log('[DocumentsTab] Starting failure detection polling...');
            appendLog('🔍 Starting failure detection polling (checking every 3s for up to 120s)...');
            
            const pollInterval = setInterval(async () => {
              pollCount++;
              console.log(`[DocumentsTab] Poll #${pollCount}/${maxPolls}`);
              
              // Stop polling after max attempts or if failure detected
              if (pollCount >= maxPolls || failureDetected) {
                console.log(`[DocumentsTab] Stopping polling. Reason: ${failureDetected ? 'failure detected' : 'max polls reached'}`);
                appendLog(`🛑 Stopping failure detection polling (${failureDetected ? 'failure detected' : 'max attempts reached'})`);
                clearInterval(pollInterval);
                return;
              }
              
              try {
                const statusResponse = await get_ipc_api().lightragApi.getStatusCounts();
                if (statusResponse.success && statusResponse.data) {
                  const statusData = statusResponse.data as any;
                  // Try both possible data structures
                  const statusCounts = statusData?.data?.status_counts || statusData?.status_counts || {};
                  // Handle both uppercase and lowercase keys
                  const newFailedCount = statusCounts?.FAILED || statusCounts?.failed || 0;
                  const processingCount = statusCounts?.PROCESSING || statusCounts?.processing || 0;
                  const pendingCount = statusCounts?.PENDING || statusCounts?.pending || 0;
                  
                  console.log(`[DocumentsTab] Poll #${pollCount}: FAILED=${newFailedCount} (was ${previousFailedCount}), PROCESSING=${processingCount}, PENDING=${pendingCount}`);
                  console.log(`[DocumentsTab] Full status counts:`, statusCounts);
                  console.log(`[DocumentsTab] Raw statusData:`, statusData);
                  
                  // Check for failures FIRST (before early stop check)
                  if (newFailedCount > previousFailedCount) {
                    failureDetected = true;
                    clearInterval(pollInterval);
                    
                    const failedDiff = newFailedCount - previousFailedCount;
                    let errorDetails = '';
                    
                    console.log(`[DocumentsTab] Detected ${failedDiff} new failed document(s), fetching details...`);
                    
                    // Fetch failed documents to get error details
                    try {
                      const failedDocsResponse = await get_ipc_api().lightragApi.getDocumentsPaginated({
                        page: 1,
                        page_size: 10,
                        status_filter: 'failed',  // Use lowercase to match backend status format
                        sort_field: 'updated_at',
                        sort_direction: 'desc'
                      });
                      
                      console.log(`[DocumentsTab] getDocumentsPaginated response:`, failedDocsResponse);
                      
                      if (!failedDocsResponse.success) {
                        console.error(`[DocumentsTab] Failed to fetch failed documents:`, failedDocsResponse.error);
                        appendLog(`❌ Failed to fetch failed document details: ${failedDocsResponse.error?.message || 'Unknown error'}`);
                      }
                      
                      if (failedDocsResponse.success && failedDocsResponse.data) {
                        const failedData = failedDocsResponse.data as any;
                        const failedDocs = failedData?.data?.documents || [];
                        
                        console.log(`[DocumentsTab] Failed docs response:`, failedDocsResponse);
                        console.log(`[DocumentsTab] Failed docs count: ${failedDocs.length}`);
                        if (failedDocs.length > 0) {
                          console.log(`[DocumentsTab] First failed doc:`, failedDocs[0]);
                        }
                        
                        // Log details of failed documents
                        if (failedDocs.length > 0) {
                          appendLog(`\n=== Failed Documents Details ===`);
                          failedDocs.slice(0, 3).forEach((doc: any) => {
                            appendLog(`📄 File: ${doc.file_path}`);
                            appendLog(`   Status: ${doc.status}`);
                            appendLog(`   Updated: ${doc.updated_at || 'N/A'}`);
                            // LightRAG saves error in 'error_msg' field (not 'error_message')
                            if (doc.error_msg) {
                              appendLog(`   Error: ${doc.error_msg}`);
                            }
                          });
                          appendLog(`================================\n`);
                          
                          // Build error summary for UI message
                          const firstDoc = failedDocs[0];
                          if (firstDoc.file_path) {
                            errorDetails = `\nLast failed: ${firstDoc.file_path}`;
                            // Include error message in UI if available
                            if (firstDoc.error_msg) {
                              // Truncate long error messages for UI display
                              const shortError = firstDoc.error_msg.length > 500 
                                ? firstDoc.error_msg.substring(0, 500) + '...'
                                : firstDoc.error_msg;
                              errorDetails += `\nError: ${shortError}`;
                            }
                          }
                        }
                      }
                    } catch (e) {
                      console.error('Failed to fetch failed document details:', e);
                      appendLog(`❌ Exception while fetching failed document details: ${e}`);
                    }
                    
                    // Always show error message, even if we couldn't fetch details
                    message.error({
                      content: `⚠️ ${failedDiff} document(s) failed to process. Please check the document list and server logs for details.${errorDetails}`,
                      duration: 10,
                      style: { maxWidth: '600px' }
                    });
                    appendLog(`⚠️ ${failedDiff} document(s) failed during processing. Check server logs for error details.`);
                    
                    // Refresh the document list to show failed status
                    await loadDocuments();
                    await loadStatusCounts();
                  }
                  
                  // Check for early stop AFTER failure detection
                  // Stop polling if no documents are pending or processing and we've checked at least twice
                  if (processingCount === 0 && pendingCount === 0 && pollCount >= 2) {
                    console.log(`[DocumentsTab] No documents pending or processing, stopping polling early`);
                    appendLog(`✅ No documents pending or processing, stopping polling early`);
                    
                    // Log current document statuses for debugging
                    if (documents.length > 0) {
                      console.log(`[DocumentsTab] Current documents in UI:`, documents.map(d => ({
                        file: d.file_path,
                        status: d.status
                      })));
                    }
                    
                    clearInterval(pollInterval);
                    // Force refresh to ensure UI shows latest status
                    await loadDocuments();
                    await loadStatusCounts();
                    return;
                  }
                }
              } catch (e) {
                console.error('Error polling for failed documents:', e);
              }
            }, 3000); // Poll every 3 seconds
          }, 2000);
      } else {
          const errorMsg = response.error?.message || 'Unknown error';
          appendLog(t('pages.knowledge.documents.errorScanning') + errorMsg);
          message.error({
            content: t('pages.knowledge.documents.errorScanning') + errorMsg,
            duration: 8,
            style: { maxWidth: '600px' }
          });
          throw new Error(errorMsg);
      }
    } catch (e: any) {
      const errorMsg = e?.message || String(e);
      appendLog(t('pages.knowledge.documents.errorScanning') + errorMsg);
      message.error({
        content: t('pages.knowledge.documents.errorScanning') + errorMsg,
        duration: 8,
        style: { maxWidth: '600px' }
      });
    }
  };

  const handleRefreshStatus = async () => {
    appendLog(t('pages.knowledge.documents.refreshingStatus'));
    await loadDocuments();
    await loadStatusCounts();
  };

  const handleClearCache = () => {
    modal.confirm({
      title: t('pages.knowledge.documents.clearCache'),
      content: t('pages.knowledge.documents.clearCacheConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          appendLog(t('pages.knowledge.documents.clearingCache'));
          const response = await get_ipc_api().lightragApi.clearCache();
          if (response.success) {
              const data = response.data as any;
              appendLog(data?.message || t('pages.knowledge.documents.cacheCleared'));
              
              // Show deleted items if available
              if (data?.deleted_items && data.deleted_items.length > 0) {
                appendLog(`Deleted ${data.deleted_items.length} items:`);
                data.deleted_items.forEach((item: string) => {
                  appendLog(`  - ${item}`);
                });
              }
              
              // Show errors if any
              if (data?.errors && data.errors.length > 0) {
                appendLog(`Errors (${data.errors.length}):`);
                data.errors.forEach((error: string) => {
                  appendLog(`  ⚠️ ${error}`);
                });
              }
              
              // Reload documents after clearing cache
              await loadDocuments();
              await loadStatusCounts();
              message.success(t('pages.knowledge.documents.cacheCleared'));
          } else {
              const errorMsg = response.error?.message || 'Unknown error';
              appendLog(t('pages.knowledge.documents.errorClearingCache') + errorMsg);
              message.error({
                content: t('pages.knowledge.documents.errorClearingCache') + errorMsg,
                duration: 8,
                style: { maxWidth: '600px' }
              });
              throw new Error(errorMsg);
          }
        } catch (e: any) {
          const errorMsg = e?.message || String(e);
          appendLog(t('pages.knowledge.documents.errorClearingCache') + errorMsg);
          message.error({
            content: t('pages.knowledge.documents.errorClearingCache') + errorMsg,
            duration: 8,
            style: { maxWidth: '600px' }
          });
        }
      }
    });
  };
  
  const handleClearLog = () => {
    setLog('');
  };

  const handleDeleteDocument = (doc: Document) => {
    const titleKey = 'pages.knowledge.documents.deleteDocument';
    const titleTrans = t(titleKey);
    // If translation is missing (returns key), fallback to Chinese
    const title = titleTrans === titleKey ? '删除文档' : titleTrans;

    modal.confirm({
      title: title,
      content: t('pages.knowledge.documents.deleteDocumentConfirm', { filePath: doc.file_path }),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          appendLog(t('pages.knowledge.documents.deletingDocument', { filePath: doc.file_path }));
          // Pass 'id' as required by the updated backend handler
          const response = await get_ipc_api().lightragApi.deleteDocument({ id: doc.id });
          if (response.success) {
              appendLog(t('pages.knowledge.documents.documentDeleted'));
              message.success(t('pages.knowledge.documents.documentDeleted'));
              // Reload documents
              await loadDocuments();
              await loadStatusCounts();
          } else {
              const errorMsg = response.error?.message || 'Unknown error';
              appendLog(t('pages.knowledge.documents.errorDeletingDocument') + errorMsg);
              message.error({
                content: t('pages.knowledge.documents.errorDeletingDocument') + errorMsg,
                duration: 8,
                style: { maxWidth: '600px' }
              });
              throw new Error(errorMsg);
          }
        } catch (e: any) {
          const errorMsg = e?.message || String(e);
          appendLog(t('pages.knowledge.documents.errorDeletingDocument') + errorMsg);
          message.error({
            content: t('pages.knowledge.documents.errorDeletingDocument') + errorMsg,
            duration: 8,
            style: { maxWidth: '600px' }
          });
        }
      }
    });
  };

  const getStatusColor = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'PROCESSED': return token.colorSuccess;
      case 'PROCESSING': return token.colorWarning;
      case 'PENDING': return token.colorTextTertiary;
      case 'FAILED': return token.colorError;
      default: return token.colorText;
    }
  };

  const getStatusText = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'PROCESSED': return t('pages.knowledge.documents.completed');
      case 'PROCESSING': return t('pages.knowledge.documents.processing');
      case 'PENDING': return t('pages.knowledge.documents.pending');
      case 'FAILED': return t('pages.knowledge.documents.failed');
      default: return status;
    }
  };

  const handleStatusFilterChange = (status: string) => {
    setStatusFilter(status === 'ALL' ? null : status);
    setCurrentPage(1); // Reset to first page on filter change
  };

  return (
    <div style={{ 
      height: '100%', 
      overflow: 'auto'
    }}>
      {contextHolder}
      <div style={{ 
        padding: '32px', 
        minHeight: '100%',
        display: 'flex', 
        flexDirection: 'column', 
        gap: 24,
        background: token.colorBgLayout
      }} data-ec-scope="lightrag-ported">
      {/* Document Management header and actions */}
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        padding: '16px 0',
        marginBottom: 8
      }}>
        <div>
          <h3 style={{ 
            margin: 0, 
            fontSize: 18, 
            fontWeight: 600, 
            color: token.colorText,
            lineHeight: 1.2
          }}>
            {t('pages.knowledge.documents.title')}
          </h3>
          <p style={{ 
            margin: '4px 0 0 0', 
            fontSize: 13, 
            color: token.colorTextSecondary 
          }}>
            {t('pages.knowledge.documents.subtitle')}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="ec-btn" onClick={handleSelectFiles}>
            <FolderOpenOutlined /> {t('pages.knowledge.documents.uploadFiles')}
          </button>
          <button className="ec-btn" onClick={handleSelectDirectory}>
            <FolderOpenOutlined /> {t('pages.knowledge.documents.importDirectory')}
          </button>
        </div>
      </div>

      {/* Pending files section - only show when files are selected */}
      {selectedFiles.length > 0 && (
        <div style={{
          background: token.colorBgContainer,
          borderRadius: 12,
          border: `1px solid ${token.colorBorder}`,
          overflow: 'hidden',
          boxShadow: isDark ? '0 2px 8px rgba(0, 0, 0, 0.15)' : '0 2px 8px rgba(0, 0, 0, 0.06)'
        }}>
          <div style={{ 
            padding: '12px 16px', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            background: isDark ? token.colorBgTextHover : token.colorBgLayout
          }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: token.colorText }}>
              {t('pages.knowledge.documents.pendingFiles')} ({selectedFiles.length})
            </span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button className="ec-btn" onClick={handleClearFiles}>
                <ClearOutlined /> {t('pages.knowledge.documents.clear')}
              </button>
              <button className="ec-btn ec-btn-primary" onClick={handleIngestFiles}>
                <UploadOutlined /> {t('pages.knowledge.documents.ingest')}
              </button>
            </div>
          </div>
          <div style={{ padding: '8px 12px', maxHeight: 120, overflowY: 'auto' }}>
            {selectedFiles.map((path, i) => (
              <div 
                key={i} 
                style={{ 
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '4px 8px',
                  borderRadius: 4,
                  background: i % 2 === 0 ? 'transparent' : (isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)')
                }}
              >
                <span 
                  style={{ 
                    flex: 1,
                    fontSize: 12,
                    color: token.colorTextSecondary,
                    whiteSpace: 'nowrap', 
                    overflow: 'hidden', 
                    textOverflow: 'ellipsis',
                    marginRight: 8
                  }} 
                  title={path}
                >
                  {getFileIcon(path)} {path}
                </span>
                <button 
                  className="ec-btn"
                  onClick={() => handleRemoveFile(path)}
                  style={{ padding: '2px 6px', fontSize: 11, minWidth: 'auto', opacity: 0.7 }}
                  title={t('common.delete')}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pending directories section - only show when directories are selected */}
      {selectedDirs.length > 0 && (
        <div style={{
          background: token.colorBgContainer,
          borderRadius: 12,
          border: `1px solid ${token.colorBorder}`,
          overflow: 'hidden',
          boxShadow: isDark ? '0 2px 8px rgba(0, 0, 0, 0.15)' : '0 2px 8px rgba(0, 0, 0, 0.06)'
        }}>
          <div style={{ 
            padding: '12px 16px', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            background: isDark ? token.colorBgTextHover : token.colorBgLayout
          }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: token.colorText }}>
              {t('pages.knowledge.documents.pendingDirs')} ({selectedDirs.length})
            </span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button className="ec-btn" onClick={handleClearDirs}>
                <ClearOutlined /> {t('pages.knowledge.documents.clear')}
              </button>
              <button className="ec-btn ec-btn-primary" onClick={handleIngestDirs}>
                <UploadOutlined /> {t('pages.knowledge.documents.ingest')}
              </button>
            </div>
          </div>
          <div style={{ padding: '8px 12px', maxHeight: 200, overflowY: 'auto' }}>
            {selectedDirs.map((dir, i) => (
              <div key={i} style={{ marginBottom: i < selectedDirs.length - 1 ? 12 : 0 }}>
                {/* 目录头部 */}
                <div 
                  style={{ 
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 8px',
                    borderRadius: 4,
                    background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span 
                      style={{ 
                        display: 'block',
                        fontSize: 12,
                        fontWeight: 600,
                        color: token.colorText,
                        whiteSpace: 'nowrap', 
                        overflow: 'hidden', 
                        textOverflow: 'ellipsis'
                      }} 
                      title={dir.path}
                    >
                      📁 {dir.path}
                    </span>
                    <span style={{ fontSize: 11, color: token.colorTextTertiary }}>
                      {dir.loading 
                        ? t('pages.knowledge.documents.scanning')
                        : t('pages.knowledge.documents.filesCount', { count: dir.files.length })
                      }
                    </span>
                  </div>
                  <button 
                    className="ec-btn"
                    onClick={() => handleRemoveDir(dir.path)}
                    style={{ padding: '2px 6px', fontSize: 11, minWidth: 'auto', opacity: 0.7 }}
                    title={t('common.delete')}
                  >
                    ✕
                  </button>
                </div>
                {/* 文件列表 */}
                {!dir.loading && dir.files.length > 0 && (
                  <div style={{ 
                    marginTop: 4, 
                    marginLeft: 16,
                    paddingLeft: 8,
                    borderLeft: `2px solid ${token.colorBorderSecondary}`
                  }}>
                    {dir.files.map((file, j) => (
                      <div 
                        key={j}
                        style={{ 
                          fontSize: 11,
                          color: token.colorTextSecondary,
                          padding: '2px 0',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis'
                        }}
                        title={file}
                      >
                        {getFileIcon(file)} {file.split('/').pop()}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Uploaded Documents section */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between', 
          marginBottom: 12,
          paddingBottom: 12,
          borderBottom: `1px solid ${token.colorBorderSecondary}`
        }}>
          <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: token.colorText }}>{t('pages.knowledge.documents.uploadedDocuments')}</h4>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="ec-btn" onClick={handleScan} title={t('pages.knowledge.documents.scanRetry')}>
              <ScanOutlined /> {t('pages.knowledge.documents.scanRetry')}
            </button>
            <button className="ec-btn" onClick={handleClearCache} title={t('pages.knowledge.documents.clearCache')}>
              <ClearOutlined /> {t('pages.knowledge.documents.clearCache')}
            </button>
            <button className="ec-btn" onClick={handleRefreshStatus} title={t('common.refresh')}>
              <UnorderedListOutlined /> {t('common.refresh')}
            </button>
            <Select 
              defaultValue="ALL" 
              style={{ width: 160 }} 
              onChange={handleStatusFilterChange}
              options={[
                { value: 'ALL', label: `${t('pages.knowledge.documents.all') || 'All'} (${statusCounts.all})` },
                { value: 'PROCESSED', label: `${t('pages.knowledge.documents.completed')} (${statusCounts.PROCESSED})` },
                { value: 'PROCESSING', label: `${t('pages.knowledge.documents.processing')} (${statusCounts.PROCESSING})` },
                { value: 'PENDING', label: `${t('pages.knowledge.documents.pending')} (${statusCounts.PENDING})` },
                { value: 'FAILED', label: `${t('pages.knowledge.documents.failed')} (${statusCounts.FAILED})` },
              ]}
            />
          </div>
        </div>

        {/* Table */}
        <div style={{ 
          height: '60vh',
          minHeight: 200,
          border: `1px solid ${token.colorBorder}`, 
          borderRadius: 16, 
          background: token.colorBgContainer,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
        }}>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '2fr 1.5fr 100px 80px 80px 130px 130px 100px', 
            gap: 8, 
            padding: '12px 16px',
            background: isDark ? token.colorBgTextHover : token.colorBgLayout,
            borderBottom: `1px solid ${token.colorBorder}`,
            fontWeight: 600,
            fontSize: 13,
            color: token.colorText
          }}>
            <div>{t('pages.knowledge.documents.fileName')}</div>
            <div>{t('pages.knowledge.documents.summary', '摘要')}</div>
            <div style={{ textAlign: 'center' }}>{t('common.status')}</div>
            <div style={{ textAlign: 'center' }}>{t('pages.knowledge.documents.length', '长度')}</div>
            <div style={{ textAlign: 'center' }}>{t('pages.knowledge.documents.chunks', '分块')}</div>
            <div style={{ textAlign: 'center' }}>{t('pages.knowledge.documents.createdAt', '创建时间')}</div>
            <div style={{ textAlign: 'center' }}>{t('pages.knowledge.documents.lastUpdated')}</div>
            <div style={{ textAlign: 'center' }}>{t('pages.knowledge.documents.actions')}</div>
          </div>
          
          {loading ? (
            <div style={{ 
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '48px 24px',
              color: token.colorTextTertiary
            }}>
              {t('common.loading')}
            </div>
          ) : documents.length === 0 ? (
            <div style={{ 
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '48px 24px',
              color: token.colorTextTertiary,
              flexDirection: 'column',
              gap: 8
            }}>
              <div style={{ fontSize: 48, opacity: 0.3 }}>📄</div>
              <div style={{ fontWeight: 600, fontSize: 15 }}>{t('pages.knowledge.documents.noDocuments')}</div>
              <div style={{ fontSize: 13 }}>{t('pages.knowledge.documents.noDocumentsDesc')}</div>
            </div>
          ) : (
            <div style={{ flex: 1, overflow: 'auto' }}>
              {documents.map((doc, idx) => (
                <div key={doc.id || doc.file_path || idx} style={{ 
                  display: 'grid', 
                  gridTemplateColumns: '2fr 1.5fr 100px 80px 80px 130px 130px 100px', 
                  gap: 8, 
                  padding: '12px 16px',
                  borderBottom: `1px solid ${token.colorBorderSecondary}`,
                  fontSize: 13,
                  alignItems: 'center',
                  transition: 'background 0.2s'
                }}>
                  <div style={{ 
                    overflow: 'hidden', 
                    textOverflow: 'ellipsis', 
                    whiteSpace: 'nowrap',
                    color: token.colorText,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6
                  }} title={doc.file_path}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{doc.file_path}</span>
                    <Tooltip title={`ID: ${doc.id}`}>
                      <InfoCircleOutlined style={{ 
                        color: token.colorTextTertiary, 
                        fontSize: 12,
                        cursor: 'pointer',
                        flexShrink: 0
                      }} />
                    </Tooltip>
                  </div>
                  <Tooltip title={doc.content_summary || ''}>
                    <div style={{ 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis', 
                      whiteSpace: 'nowrap',
                      color: token.colorTextSecondary,
                      fontSize: 12,
                      cursor: doc.content_summary ? 'pointer' : 'default'
                    }}>
                      {doc.content_summary || '-'}
                    </div>
                  </Tooltip>
                  <div style={{ 
                    textAlign: 'center',
                    color: getStatusColor(doc.status),
                    fontWeight: 600
                  }}>
                    {getStatusText(doc.status)}
                  </div>
                  <div style={{ 
                    textAlign: 'center',
                    color: token.colorTextSecondary,
                    fontSize: 12
                  }}>
                    {doc.content_length ? doc.content_length.toLocaleString() : '-'}
                  </div>
                  <div style={{ 
                    textAlign: 'center',
                    color: token.colorTextSecondary,
                    fontSize: 12
                  }}>
                    {doc.chunks_count ?? '-'}
                  </div>
                  <div style={{ 
                    textAlign: 'center',
                    color: token.colorTextSecondary,
                    fontSize: 12
                  }}>
                    {doc.created_at ? new Date(doc.created_at).toLocaleString('zh-CN', { 
                      year: 'numeric', 
                      month: '2-digit', 
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit'
                    }) : '-'}
                  </div>
                  <div style={{ 
                    textAlign: 'center',
                    color: token.colorTextSecondary,
                    fontSize: 12
                  }}>
                    {doc.updated_at ? new Date(doc.updated_at).toLocaleString('zh-CN', { 
                      year: 'numeric', 
                      month: '2-digit', 
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit'
                    }) : '-'}
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <button 
                      className="ec-btn-small"
                      onClick={() => handleDeleteDocument(doc)}
                      style={{
                        padding: '4px 12px',
                        fontSize: 12,
                        background: token.colorErrorBg,
                        color: token.colorError,
                        border: `1px solid ${token.colorErrorBorder}`,
                        borderRadius: 6,
                        cursor: 'pointer',
                        transition: 'all 0.2s'
                      }}
                    >
                      {t('common.delete')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {/* Pagination Footer */}
          <div style={{
            padding: '12px 16px',
            borderTop: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            justifyContent: 'flex-end'
          }}>
            <Pagination 
              current={currentPage} 
              pageSize={pageSize} 
              total={totalDocs} 
              onChange={(page, size) => {
                setCurrentPage(page);
                setPageSize(size);
              }}
              size="small"
              showTotal={(total) => t('pages.knowledge.documents.totalItems', { total })}
            />
          </div>
        </div>
      </div>

      {/* Log console */}
      <div style={{ 
        background: isDark ? token.colorBgElevated : token.colorBgContainer, 
        borderRadius: 16, 
        border: `1px solid ${token.colorBorder}`,
        overflow: 'hidden'
      }}>
        {/* Console header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          background: isDark ? token.colorBgTextHover : token.colorBgLayout
        }}>
          <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: token.colorText }}>
            {t('pages.knowledge.documents.console', '控制台')}
          </h4>
          <button 
            className="ec-btn-small" 
            onClick={handleClearLog} 
            title={t('pages.knowledge.documents.clearLog')}
            style={{
              padding: '4px 12px',
              fontSize: 12,
              background: token.colorBgContainer,
              color: token.colorTextSecondary,
              border: `1px solid ${token.colorBorder}`,
              borderRadius: 6,
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
          >
            <ClearOutlined style={{ marginRight: 4 }} />
            {t('pages.knowledge.documents.clearLog')}
          </button>
        </div>
        {/* Console content */}
        <div style={{ 
          padding: 16, 
          minHeight: 100,
          maxHeight: 180,
          overflow: 'auto',
          fontFamily: 'Monaco, Consolas, "Courier New", monospace',
          fontSize: 13,
          lineHeight: 1.8,
          color: token.colorText,
          boxShadow: isDark ? 'inset 0 2px 8px rgba(0, 0, 0, 0.2)' : 'inset 0 2px 8px rgba(0, 0, 0, 0.05)'
        }}>
          {log ? (
            <pre
              style={{
                margin: 0,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {log}
            </pre>
          ) : (
            <span style={{ opacity: 0.5, color: token.colorTextTertiary }}>
              {t('pages.knowledge.documents.consoleOutput')}
            </span>
          )}
        </div>
      </div>

      {/* Scoped styles */}
      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 10px;
          padding: 10px 14px;
          font-size: 14px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        [data-ec-scope="lightrag-ported"] .ec-input:focus {
          outline: none;
          border-color: ${token.colorPrimary};
          box-shadow: 0 0 0 2px ${token.colorPrimaryBg};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 10px;
          padding: 10px 18px;
          cursor: pointer;
          font-size: 14px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          font-weight: 500;
          box-shadow: ${isDark ? '0 2px 8px rgba(0, 0, 0, 0.15)' : '0 2px 8px rgba(0, 0, 0, 0.05)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:hover {
          border-color: ${token.colorPrimary};
          color: ${token.colorPrimary};
          transform: translateY(-2px);
          box-shadow: ${isDark ? '0 4px 12px rgba(24, 144, 255, 0.3)' : '0 4px 12px rgba(24, 144, 255, 0.2)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary {
          background: ${token.colorPrimary};
          color: #ffffff;
          border-color: ${token.colorPrimary};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary:hover {
          background: ${token.colorPrimaryHover};
          border-color: ${token.colorPrimaryHover};
          color: #ffffff;
          transform: translateY(-2px);
          box-shadow: 0 6px 16px rgba(24, 144, 255, 0.4);
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        [data-ec-scope="lightrag-ported"] .ec-file-input {
          padding: 12px;
          border: 2px dashed ${token.colorBorder};
          border-radius: 10px;
          background: ${isDark ? token.colorBgElevated : token.colorBgLayout};
          color: ${token.colorText};
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          cursor: pointer;
          font-size: 13px;
        }
        [data-ec-scope="lightrag-ported"] .ec-file-input:hover {
          border-color: ${token.colorPrimary};
          background: ${token.colorPrimaryBg};
        }
        [data-ec-scope="lightrag-ported"] .ec-file-input::file-selector-button {
          padding: 6px 12px;
          border: 1px solid ${token.colorBorder};
          border-radius: 6px;
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          cursor: pointer;
          margin-right: 12px;
          font-size: 13px;
          font-weight: 500;
          transition: all 0.2s;
        }
        [data-ec-scope="lightrag-ported"] .ec-file-input::file-selector-button:hover {
          background: ${token.colorPrimary};
          color: #ffffff;
          border-color: ${token.colorPrimary};
        }
      `}</style>
      </div>
    </div>
  );
};

export default DocumentsTab;
