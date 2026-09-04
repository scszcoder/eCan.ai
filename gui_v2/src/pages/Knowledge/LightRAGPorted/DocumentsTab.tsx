import { theme, Pagination, Select, Modal, App, Tooltip, Progress, Switch } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { ScanOutlined, UnorderedListOutlined, ClearOutlined, FolderOpenOutlined, UploadOutlined, InfoCircleOutlined, DeleteOutlined, StopOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import React, { useState, useEffect, useRef } from 'react';
import type { ProcessingProgress } from '@/services/ipc/lightragApi';
import { useWorkspace } from './useWorkspace';

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

// 从文件路径中提取文件名
const getFileName = (filePath: string | null | undefined): string => {
  if (!filePath) return 'Unknown file';
  // Windows 或 Unix 路径分隔符
  const parts = filePath.split(/[\\/]/);
  const filename = parts[parts.length - 1];
  return filename || filePath;
};

// 从 LightRAG 1.5.6 pipeline_status.latest_message 解析 chunk-level 进度。
// 最新消息格式（去前缀空白后）:
//   "Chunk 5 of 60 extracted 24 Ent + 28 Rel doc-<id>-chunk-004"
//   "Chunk10 of 60 extracted 18 Ent + 22 Rel doc-<id>-chunk-009"
// 返回 null 表示消息不可解析（解析前/解析后/跨 workspace 等情况），调用方应回退到估算。
interface ChunkProgress {
  current: number;
  total: number;
  docId: string;
}

const CHUNK_PROGRESS_REGEX =
  /Chunk\s+(\d+)\s+of\s+(\d+)\s+extracted\s+(\d+)\s+Ent\s*\+\s*(\d+)\s+Rel\s+(doc-[0-9a-f]+)-chunk-\d+/i;

const parseLatestChunkProgress = (message: string | null | undefined): ChunkProgress | null => {
  if (!message) return null;
  const match = CHUNK_PROGRESS_REGEX.exec(message);
  if (!match) return null;
  const [, currentRaw, totalRaw, , , docId] = match;
  const current = Number(currentRaw);
  const total = Number(totalRaw);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
  return { current, total, docId };
};

const chunkProgressToPercent = (progress: ChunkProgress): number =>
  Math.max(0, Math.min(100, Math.round((progress.current / progress.total) * 100)));

const DocumentsTab: React.FC = () => {
  const { message } = App.useApp();
  const [modal, contextHolder] = Modal.useModal();
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [selectedDirs, setSelectedDirs] = useState<DirScanResult[]>([]);
  const [log, setLog] = useState<string>('');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [statusCounts, setStatusCounts] = useState({ all: 0, PROCESSED: 0, PROCESSING: 0, PENDING: 0, FAILED: 0 });
  const [loading, setLoading] = useState(false);
  const [processingProgress, setProcessingProgress] = useState<ProcessingProgress | null>(null);
  const [documentProgress, setDocumentProgress] = useState<Map<string, number>>(new Map());
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const failurePollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const scanPollingStartTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const statusCountsInFlightRef = useRef(false);
  const consoleRef = useRef<HTMLDivElement | null>(null);
  const batchCancelRequestedRef = useRef(false);
  const batchSubmittingRef = useRef(false);
  // Mirror of `documents` that async closures (e.g. pollUntilDeleted started
  // before loadDocuments() resolves) can read for the freshest list.
  const documentsRef = useRef<Document[]>([]);
  const [autoStopOnFailure, setAutoStopOnFailure] = useState(true); // 默认启用自动停止
  const [consoleCollapsed, setConsoleCollapsed] = useState(false); // Console折叠状态，默认展开
  // LightRAG workspace (tenant) for scoping ingestion and document queries.
  // Empty = server default. Controlled by the global header picker.
  const [workspace] = useWorkspace();

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalDocs, setTotalDocs] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [ingestBatchSize, setIngestBatchSize] = useState(4);
  

  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const appendLog = (line: string) => {
    setLog(prev => prev ? prev + '\n' + line : line);
    // Auto-scroll to bottom when new log is added
    setTimeout(() => {
      if (consoleRef.current) {
        consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
      }
    }, 100);
  };

  const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

  const chunkPaths = (paths: string[], batchSize: number) => {
    const chunks: string[][] = [];
    for (let i = 0; i < paths.length; i += batchSize) {
      chunks.push(paths.slice(i, i + batchSize));
    }
    return chunks;
  };

  const requestStopPendingBatches = (reason?: string) => {
    if (batchSubmittingRef.current && !batchCancelRequestedRef.current) {
      batchCancelRequestedRef.current = true;
      appendLog(reason || '已停止后续批次提交，等待当前批次结束...');
    }
  };

  const waitForProcessingBackpressure = async () => {
    for (let attempt = 0; attempt < 30; attempt++) {
      if (batchCancelRequestedRef.current) {
        return;
      }

      try {
        const response = await get_ipc_api().lightragApi.getProcessingProgress(undefined, workspace || undefined);
        if (response.success && response.data) {
          const progressData = response.data as any;
          const processingCount = progressData.processing_count || 0;
          if (processingCount <= 1) {
            return;
          }
        } else {
          return;
        }
      } catch {
        return;
      }

      await sleep(1000);
    }
  };

  const ingestFilesInBatches = async (paths: string[], sourceLabel: string) => {
    const sanitizedPaths = paths.filter(Boolean);
    if (sanitizedPaths.length === 0) {
      return false;
    }

    // Validate against the parser configuration that is actually persisted
    // and used by LightRAG. MinerU 3.4.4 uses a strict format allowlist.
    try {
      const settingsResponse = await get_ipc_api().lightragApi.getSettings();
      const persisted = (settingsResponse.data || {}) as Record<string, string>;
      const routing = (persisted.LIGHTRAG_PARSER || '').toLowerCase();
      if (routing.includes('mineru')) {
        const mineruSupported = /\.(pdf|docx|pptx|xlsx|png|jpe?g|jp2|webp|gif|bmp|tiff)$/i;
        const unsupported = sanitizedPaths.filter(path => !mineruSupported.test(path));
        if (unsupported.length > 0) {
          const names = unsupported.slice(0, 5).map(getFileName).join('、');
          const suffix = unsupported.length > 5 ? ` 等 ${unsupported.length} 个文件` : '';
          const detail = t('pages.knowledge.documents.mineruUnsupportedFormat', {
            files: `${names}${suffix}`,
          });
          appendLog(`⚠️ ${detail}`);
          message.warning({ content: detail, duration: 8 });
          return false;
        }
      }
    } catch (error) {
      console.warn('[DocumentsTab] Could not preflight parser file formats:', error);
      // The backend performs the same validation, so a settings-read failure
      // cannot bypass the protection.
    }

    if (batchSubmittingRef.current) {
      appendLog('已有批次提交任务正在执行，请等待当前任务完成');
      return false;
    }

    const batchSize = Math.max(1, ingestBatchSize || 1);
    const batches = chunkPaths(sanitizedPaths, batchSize);
    batchCancelRequestedRef.current = false;
    batchSubmittingRef.current = true;

    try {
      appendLog(`${sourceLabel}，共 ${sanitizedPaths.length} 个文件，按批次提交（每批 ${batchSize} 个）`);

      for (let i = 0; i < batches.length; i++) {
        if (batchCancelRequestedRef.current) {
          appendLog(`已取消后续批次提交，停止在第 ${i + 1}/${batches.length} 批之前`);
          return false;
        }

        const batch = batches[i];
        appendLog(`开始提交第 ${i + 1}/${batches.length} 批，本批 ${batch.length} 个文件`);

        const response = await get_ipc_api().lightragApi.ingestFiles({ paths: batch, workspace: workspace || undefined });
        if (!response.success) {
          throw new Error(response.error?.message || `第 ${i + 1} 批提交失败`);
        }

        appendLog(`第 ${i + 1}/${batches.length} 批提交成功`);

        if (batchCancelRequestedRef.current) {
          appendLog(`第 ${i + 1}/${batches.length} 批提交后检测到停止请求，跳过扫描`);
          return false;
        }

        appendLog(`开始扫描第 ${i + 1}/${batches.length} 批文件`);
        const scanResponse = await get_ipc_api().lightragApi.scan({ workspace: workspace || undefined });
        if (!scanResponse.success) {
          throw new Error(scanResponse.error?.message || `第 ${i + 1} 批扫描失败`);
        }
        appendLog(`第 ${i + 1}/${batches.length} 批已触发扫描`);

        if (i < batches.length - 1) {
          await waitForProcessingBackpressure();
        }
      }

      if (batchCancelRequestedRef.current) {
        appendLog('批次提交流程已停止，未继续发送剩余文件');
        return false;
      }

      appendLog(`所有批次提交完成，共 ${batches.length} 批`);
      return true;
    } finally {
      batchSubmittingRef.current = false;
    }
  };

  // Load documents on mount and whenever the workspace, page, page-size or
  // status filter changes. Switching workspace from the global header
  // picker therefore refreshes the grid for the newly selected tenant.
  React.useEffect(() => {
    loadDocuments();
  }, [currentPage, pageSize, statusFilter, workspace]);

  // Start progress polling when there are processing/pending documents
  useEffect(() => {
    const hasActiveProcessing = statusCounts.PROCESSING > 0 || statusCounts.PENDING > 0;
    
    if (hasActiveProcessing && !progressIntervalRef.current) {
      // Start polling
      startProgressPolling();
    } else if (!hasActiveProcessing && progressIntervalRef.current) {
      // Stop polling
      stopProgressPolling();
    }
    
    return () => {
      stopProgressPolling();
      if (scanPollingStartTimeoutRef.current) {
        clearTimeout(scanPollingStartTimeoutRef.current);
        scanPollingStartTimeoutRef.current = null;
      }
      if (failurePollIntervalRef.current) {
        clearInterval(failurePollIntervalRef.current);
        failurePollIntervalRef.current = null;
      }
    };
  }, [statusCounts.PROCESSING, statusCounts.PENDING]);

  useEffect(() => {
    const loadIngestBatchSize = async () => {
      try {
        const response = await get_ipc_api().lightragApi.getSettings();
        if (response.success && response.data) {
          const loadedSettings = response.data as Record<string, string>;
          const configuredBatchSize = Number(loadedSettings['MAX_PARALLEL_INSERT'] || '2');
          if (!Number.isNaN(configuredBatchSize) && configuredBatchSize > 0) {
            setIngestBatchSize(configuredBatchSize);
          }
        }
      } catch (e) {
        console.error('[DocumentsTab] Failed to load ingest batch size from settings:', e);
      }
    };

    loadIngestBatchSize();
  }, []);

  const stopFailureDetectionPolling = () => {
    if (failurePollIntervalRef.current) {
      clearInterval(failurePollIntervalRef.current);
      failurePollIntervalRef.current = null;
    }
    statusCountsInFlightRef.current = false;
  };

  const cancelScanPollingStartTimeout = () => {
    if (scanPollingStartTimeoutRef.current) {
      clearTimeout(scanPollingStartTimeoutRef.current);
      scanPollingStartTimeoutRef.current = null;
    }
  };

  const startFailureDetectionPolling = (previousFailedCount: number) => {
    stopFailureDetectionPolling();

    let pollCount = 0;
    const maxPolls = 40;
    let failureDetected = false;
    let completedWithoutFailure = false;

    console.log('[DocumentsTab] Starting failure detection polling...');
    appendLog('🔍 开始失败检测轮询（每 3 秒检查一次，最长 120 秒）...');

    failurePollIntervalRef.current = setInterval(async () => {
      pollCount++;
      console.log(`[DocumentsTab] Poll #${pollCount}/${maxPolls}`);

      if (failureDetected || completedWithoutFailure || pollCount >= maxPolls) {
        const reason = failureDetected
          ? 'failure detected'
          : completedWithoutFailure
            ? 'processing completed'
            : 'timeout reached';
        console.log(`[DocumentsTab] Stopping polling. Reason: ${reason}`);
        if (failureDetected) {
          appendLog('🛑 检测到失败文档，停止失败检测轮询');
        } else if (completedWithoutFailure) {
          appendLog('✅ 当前处理已结束，停止失败检测轮询');
        } else {
          appendLog('ℹ️ 失败检测轮询已结束（120 秒内未检测到新的失败文档）');
        }
        stopFailureDetectionPolling();
        return;
      }

      if (statusCountsInFlightRef.current) {
        return;
      }

      statusCountsInFlightRef.current = true;
      try {
        // Counts can be zero while LightRAG is parsing or analyzing. Progress
        // also includes the authoritative pipeline busy flag.
        const statusResponse = await get_ipc_api().lightragApi.getProcessingProgress(undefined, workspace || undefined);
        if (statusResponse.success && statusResponse.data) {
          const statusData = statusResponse.data as any;
          const currentStatusCounts = statusData?.data || statusData;
          const newFailedCount = currentStatusCounts?.failed_count || 0;
          const processingCount = currentStatusCounts?.processing_count || 0;
          const pendingCount = currentStatusCounts?.pending_count || 0;
          const pipelineBusy = Boolean(
            currentStatusCounts?.pipeline_busy || currentStatusCounts?.pipeline?.busy
          );

          console.log(`[DocumentsTab] Poll #${pollCount}: FAILED=${newFailedCount} (was ${previousFailedCount}), PROCESSING=${processingCount}, PENDING=${pendingCount}`);
          console.log(`[DocumentsTab] Full status counts:`, currentStatusCounts);
          console.log(`[DocumentsTab] Raw statusData:`, statusData);

          if (newFailedCount > previousFailedCount) {
            failureDetected = true;
            stopFailureDetectionPolling();

            const failedDiff = newFailedCount - previousFailedCount;
            let errorDetails = '';

            console.log(`[DocumentsTab] Detected ${failedDiff} new failed document(s), fetching details...`);

            try {
              const failedDocsResponse = await get_ipc_api().lightragApi.getDocumentsPaginated({
                page: 1,
                page_size: 10,
                status_filter: 'failed',
                workspace: workspace || undefined,
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

                if (failedDocs.length > 0) {
                  appendLog(`\n=== Failed Documents Details ===`);
                  failedDocs.slice(0, 3).forEach((doc: any) => {
                    appendLog(`📄 File: ${doc.file_path}`);
                    appendLog(`   Status: ${doc.status}`);
                    appendLog(`   Updated: ${doc.updated_at || 'N/A'}`);
                    if (doc.error_msg) {
                      appendLog(`   Error: ${doc.error_msg}`);
                    }
                  });
                  appendLog(`================================\n`);

                  const firstDoc = failedDocs[0];
                  if (firstDoc.file_path) {
                    errorDetails = `\nLast failed: ${firstDoc.file_path}`;
                    if (firstDoc.error_msg) {
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

            message.error({
              content: `⚠️ ${failedDiff} document(s) failed to process. Please check the document list and server logs for details.${errorDetails}`,
              duration: 10,
              style: { maxWidth: '600px' }
            });
            appendLog(`⚠️ ${failedDiff} document(s) failed during processing. Check server logs for error details.`);
            await loadDocuments();
            return;
          }

          if (!pipelineBusy && processingCount === 0 && pendingCount === 0 && pollCount >= 2) {
            console.log(`[DocumentsTab] No documents pending or processing, stopping polling early`);
            appendLog('✅ 当前没有待处理或处理中任务，结束失败检测轮询');

            if (documents.length > 0) {
              console.log(`[DocumentsTab] Current documents in UI:`, documents.map(d => ({
                file: d.file_path,
                status: d.status
              })));
            }

            completedWithoutFailure = true;
            await loadDocuments();
            return;
          }
        }
      } catch (e) {
        console.error('Error polling for failed documents:', e);
      } finally {
        statusCountsInFlightRef.current = false;
      }
    }, 3000);
  };

  const startProgressPolling = () => {
    if (progressIntervalRef.current) return;
    
    // Poll immediately
    fetchProgress();
    
    // Then poll every 3 seconds
    progressIntervalRef.current = setInterval(() => {
      fetchProgress();
    }, 3000);
  };

  const stopProgressPolling = () => {
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current);
      progressIntervalRef.current = null;
      
      // Refresh document list when polling stops (processing completed)
      console.log('[DocumentsTab] Processing completed, refreshing document list...');
      loadDocuments();
    }
    setProcessingProgress(null);
  };

  const fetchProgress = async () => {
    try {
      const response = await get_ipc_api().lightragApi.getProcessingProgress(undefined, workspace || undefined);
      if (response.success && response.data) {
        console.log('[DocumentsTab] Progress update:', response.data);
        setProcessingProgress(response.data);
        
        const progressData = response.data as any;
        const failedCount = progressData.failed_count || 0;
        const processingCount = progressData.processing_count || 0;
        const pendingCount = progressData.pending_count || 0;
        
        // Check if there are failed documents and pending documents
        // If processing is done (processing_count = 0) and there are failures with pending docs
        // And auto-stop is enabled
        if (autoStopOnFailure && failedCount > 0 && processingCount === 0 && pendingCount > 0) {
          console.log('[DocumentsTab] Detected failed documents with pending ones, cancelling pipeline...');
          requestStopPendingBatches(`检测到 ${failedCount} 个文档处理失败，已停止后续批次提交`);
          
          // Cancel pipeline to prevent pending documents from being processed
          try {
            await get_ipc_api().lightragApi.abortDocument({ id: 'auto-cancel', workspace: workspace || undefined });
            console.log('[DocumentsTab] Pipeline cancelled due to failures');
            appendLog(`检测到 ${failedCount} 个文档处理失败，已停止后续批次并请求停止当前处理`);
            message.warning(`检测到 ${failedCount} 个文档处理失败，已停止后续批次并请求停止当前处理`);
            
            // Stop polling
            stopProgressPolling();
            
            // Reload documents after a short delay
            setTimeout(() => {
              loadDocuments();
            }, 1000);
            
            return; // Exit early, don't continue processing
          } catch (e) {
            console.error('[DocumentsTab] Failed to auto-cancel pipeline:', e);
          }
        }
        
        // Refresh document list to get latest status (silent to avoid flicker)
        // This ensures the UI shows updated document statuses during processing
        loadDocuments(true);
        
        // Calculate individual document progress. LightRAG 1.5.6 publishes
        // a real per-document counter in pipeline.latest_message; for any
        // document the latest_message does not name, fall back to a low
        // indeterminate hint so the bar still moves.
        const newProgress = new Map<string, number>();
        const latestMessage = progressData.pipeline?.latest_message;
        const chunkProgress = parseLatestChunkProgress(latestMessage);
        const chunkDocPercent = chunkProgress ? chunkProgressToPercent(chunkProgress) : 0;

        documents.forEach(doc => {
          const status = doc.status?.toUpperCase();
          if (chunkProgress && doc.id === chunkProgress.docId) {
            newProgress.set(doc.id, chunkDocPercent);
          } else if (status === 'PROCESSING') {
            newProgress.set(doc.id, 25);
          } else if (status === 'PENDING') {
            newProgress.set(doc.id, 5);
          }
        });

        setDocumentProgress(newProgress);
      }
    } catch (e) {
      console.error('Error fetching progress:', e);
    }
  };

  // 支持的文件类型（与后端保持一致）
  const SUPPORTED_FILE_EXTENSIONS = [
    'txt', 'md', 'markdown', 'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'rtf', 'odt', 'tex', 'epub',
    'html', 'htm', 'csv', 'json', 'xml', 'yaml', 'yml', 'log', 'conf', 'ini',
    'properties', 'sql', 'bat', 'sh', 'c', 'cpp', 'py', 'java', 'js', 'ts',
    'swift', 'go', 'rb', 'php', 'css', 'scss', 'less', 'png', 'jpg', 'jpeg',
    'jp2', 'webp', 'gif', 'bmp', 'tif', 'tiff'
  ];

  const handleSelectFiles = async () => {
    try {
      // 5 minutes timeout for user interaction
      // 添加文件类型过滤器
      const filters = [
        {
          name: t('pages.knowledge.documents.supportedFiles'),
          extensions: SUPPORTED_FILE_EXTENSIONS
        },
        {
          name: t('pages.knowledge.documents.allFiles'),
          extensions: ['*']
        }
      ];
      const response = await get_ipc_api().executeRequest<any>('fs.selectFiles', { multiple: true, filters }, 300000);
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
      const success = await ingestFilesInBatches(
        selectedFiles,
        t('pages.knowledge.documents.ingestingFiles', { count: selectedFiles.length })
      );
      if (!success) {
        return;
      }

      setSelectedFiles([]);
      appendLog(t('pages.knowledge.documents.scanStarted'));
      startProgressPolling();
      setTimeout(async () => {
        await loadDocuments();
        startFailureDetectionPolling(statusCounts.FAILED);
      }, 2000);
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
      
      const success = await ingestFilesInBatches(
        allFiles,
        t('pages.knowledge.documents.ingestingFilesFromDirs', { fileCount: allFiles.length, dirCount: selectedDirs.length })
      );
      if (!success) {
        return;
      }

      setSelectedDirs([]);
      appendLog(t('pages.knowledge.documents.scanStarted'));
      startProgressPolling();
      setTimeout(async () => {
        await loadDocuments();
        startFailureDetectionPolling(statusCounts.FAILED);
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

  const loadDocuments = async (silentRefresh: boolean = false, retryCount: number = 0) => {
    // LightRAG cold-start takes 6-10s on first launch (transformers/torch/
    // langchain_core imported eagerly inside LightRAG 1.5.6's chunker
    // chain). Default retries (3 × 2s = 6s) fall short on slow machines,
    // so the user sees an empty grid + red toast. Bump to 10 × 2s = 20s
    // so even 8s startups finish before we give up. Each retry only
    // sleeps on cold start — once the server is up, retries are no-ops.
    const MAX_RETRIES = 10;
    const RETRY_DELAY = 2000; // 2 seconds
    const isConnectionErrorMessage = (msg: string) => {
      const m = (msg || '').toLowerCase();
      return m.includes('connection') ||
             m.includes('refused') ||
             m.includes('max retries exceeded') ||
             m.includes('failed to establish a new connection');
    };
    
    try {
      if (!silentRefresh) {
        setLoading(true);
        // Clear documents list on first load to avoid duplicates during retry
        if (retryCount === 0) {
          setDocuments([]);
        }
      }
      
      // Use paginated API
      const response = await get_ipc_api().lightragApi.getDocumentsPaginated({
        page: currentPage,
        page_size: pageSize,
        status_filter: statusFilter === 'ALL' ? null : statusFilter,
        workspace: workspace || undefined,
        sort_field: 'updated_at',
        sort_direction: 'desc'
      });

      console.log('[DocumentsTab] Raw API response:', response);
      
      // Check if server is not ready (connection refused) and retry
      if (!response.success && retryCount < MAX_RETRIES) {
        const errorMsg = response.error?.message || '';
        const isConnectionError = isConnectionErrorMessage(errorMsg);
        
        if (isConnectionError) {
          console.log(`[DocumentsTab] Server not ready, retrying in ${RETRY_DELAY}ms... (attempt ${retryCount + 1}/${MAX_RETRIES})`);
          if (!silentRefresh) {
            appendLog(t('pages.knowledge.documents.waitingForServer', { 
              defaultValue: `Waiting for LightRAG server... (attempt ${retryCount + 1}/${MAX_RETRIES})` 
            }));
          }
          await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
          return loadDocuments(silentRefresh, retryCount + 1);
        }
      }

      // Only log a real terminal error. A connection refusal handled above is
      // normal while LightRAG is restarting and should not pollute the console.
      if (!response.success) {
        console.error('[DocumentsTab] API call failed with error:', {
          code: response.error?.code,
          message: response.error?.message,
          details: response.error?.details
        });
      }

      if (response.success && response.data) {
          const res = response.data as any;
          // 支持两种数据结构：res.documents 或 res.data.documents
          const docsArray = res?.documents || res?.data?.documents;
          const pagination = res?.pagination || res?.data?.pagination;
          const statusCountsData = res?.status_counts || res?.data?.status_counts;
          
          // 更新 status counts（如果返回了）
          if (statusCountsData) {
            const normalizedCounts: Record<string, number> = {};
            Object.keys(statusCountsData).forEach(key => {
              normalizedCounts[key.toUpperCase()] = statusCountsData[key];
            });
            // 只计算 UI 显示的状态总数（PROCESSED, PROCESSING, PENDING, FAILED）
            // PREPROCESSED 等中间状态不计入，避免数量不一致
            const processed = normalizedCounts.PROCESSED || 0;
            const processing = normalizedCounts.PROCESSING || 0;
            const pending = normalizedCounts.PENDING || 0;
            const failed = normalizedCounts.FAILED || 0;
            const all = processed + processing + pending + failed;
            setStatusCounts({
              all,
              PROCESSED: processed,
              PROCESSING: processing,
              PENDING: pending,
              FAILED: failed
            });
          }
          
          if (Array.isArray(docsArray)) {
            documentsRef.current = docsArray;
            // Optimize: Only update if documents actually changed (for silent refresh)
            if (silentRefresh) {
              // Compare and only update if there are actual changes
              const hasChanges = JSON.stringify(docsArray) !== JSON.stringify(documents);
              if (hasChanges) {
                setDocuments(docsArray);
              }
            } else {
              // Full refresh - always update
              setDocuments(docsArray);
            }
            
            setTotalDocs(pagination?.total_count || docsArray.length);
            
            if (!silentRefresh) {
              if (docsArray.length > 0) {
                appendLog(t('pages.knowledge.documents.loadedDocuments', { count: docsArray.length, page: currentPage }));
              } else {
                console.warn('[DocumentsTab] Documents array is empty');
                appendLog(t('pages.knowledge.documents.noDocumentsFound'));
              }
            }
          } else if (res && res.data && res.data.statuses) {
            console.log('[DocumentsTab] Using fallback statuses structure');
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
          console.error('[DocumentsTab] API call failed:', response);
          const errorMsg = 'Error loading documents: ' + (response.error?.message || response.error?.code || 'Unknown error');
          appendLog(errorMsg);
          message.error(errorMsg);
      }
    } catch (e: any) {
      console.error('[DocumentsTab] Exception in loadDocuments:', e);

      const rawMessage = e?.message || e?.error?.message || String(e);
      if (retryCount < MAX_RETRIES && isConnectionErrorMessage(rawMessage)) {
        console.log(`[DocumentsTab] Exception indicates server not ready, retrying in ${RETRY_DELAY}ms... (attempt ${retryCount + 1}/${MAX_RETRIES})`);
        if (!silentRefresh) {
          appendLog(t('pages.knowledge.documents.waitingForServer', {
            defaultValue: `Waiting for LightRAG server... (attempt ${retryCount + 1}/${MAX_RETRIES})`
          }));
        }
        await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
        return loadDocuments(silentRefresh, retryCount + 1);
      }

      const errorMsg = 'Error loading documents: ' + rawMessage;
      appendLog(errorMsg);
      message.error(errorMsg);
    } finally {
      if (!silentRefresh) {
        setLoading(false);
      }
    }
  };

  const handleScan = async () => {
    try {
      appendLog(t('pages.knowledge.documents.startingScan'));

      cancelScanPollingStartTimeout();
      stopFailureDetectionPolling();
      
      // Record current failed count before scan
      const previousFailedCount = statusCounts.FAILED;
      
      const response = await get_ipc_api().lightragApi.scan({ workspace: workspace || undefined });
      if (response.success && response.data) {
          const res = response.data as any;
          appendLog(t('pages.knowledge.documents.scanStarted') + JSON.stringify(res));
          message.success(t('pages.knowledge.documents.scanStarted') + (res.message || ''));
          
          // Reload documents after scan and start polling for failures
          scanPollingStartTimeoutRef.current = setTimeout(async () => {
            await loadDocuments();
            startFailureDetectionPolling(previousFailedCount);
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
          const response = await get_ipc_api().lightragApi.clearCache({ workspace: workspace || undefined });
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

  const handleAbortDocument = (doc: Document) => {
    modal.confirm({
      title: t('pages.knowledge.documents.stopProcessing'),
      content: t('pages.knowledge.documents.stopProcessingConfirm', { filePath: doc.file_path }),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const docId = doc.id;
          requestStopPendingBatches('已停止后续批次提交，正在请求停止当前处理...');
          appendLog(t('pages.knowledge.documents.stoppingDocument'));
          
          // Use graceful stop (cancel_pipeline API sets cancellation flag)
          const response = await get_ipc_api().lightragApi.abortDocument({ id: docId, workspace: workspace || undefined });
          
          if (response.success) {
              appendLog('已停止后续批次提交，并已发送停止当前处理请求');
              message.success('已停止后续批次提交，并已发送停止当前处理请求');

              // Stop normal polling, start custom polling for this specific document
              console.log('[DocumentsTab] Pipeline cancelled, polling until document becomes deletable...');
              stopProgressPolling();

              // Force an immediate non-silent refresh so the UI flips out of
              // 'processing' right away instead of waiting for the polling loop
              // (silentRefresh=true skips setDocuments when JSON.stringify
              // matches the cached array, which can hold the row stale for
              // many seconds after the server already flipped it to FAILED).
              await loadDocuments(false);

              let pollCount = 0;
              const maxPolls = 20; // Max 20 polls (60 seconds with 3s interval)
              const pollInterval = 3000;
              
              const pollUntilDeletable = async () => {
                pollCount++;
                console.log(`[DocumentsTab] Poll ${pollCount}/${maxPolls} - checking if document is deletable...`);
                
                // Refresh document list
                await loadDocuments();
                
                // Check the specific document's status
                const docsResponse = await get_ipc_api().lightragApi.getDocumentsPaginated({
                  page: 1, page_size: 100, status_filter: null, sort_field: 'updated_at', sort_direction: 'desc',
                  workspace: workspace || undefined,
                });
                
                if (docsResponse.success && docsResponse.data) {
                  const docsData = docsResponse.data as any;
                  const allDocs = docsData.documents || docsData.items || [];
                  const targetDoc = allDocs.find((d: any) => d.id === docId);
                  
                  if (targetDoc) {
                    const status = targetDoc.status?.toUpperCase();
                    console.log(`[DocumentsTab] Document ${docId} status: ${status}`);
                    
                    // Document is deletable when status is FAILED, PROCESSED, or not found
                    if (status === 'FAILED' || status === 'PROCESSED') {
                      console.log('[DocumentsTab] ✅ Document is now deletable');
                      appendLog(`文档已停止，状态: ${status}`);
                      await loadDocuments();
                      return; // Done
                    }
                  } else {
                    // Document not found - might have been deleted
                    console.log('[DocumentsTab] ✅ Document not found, stop complete');
                    await loadDocuments();
                    return;
                  }
                }
                
                // Continue polling if not done
                if (pollCount < maxPolls) {
                  setTimeout(pollUntilDeletable, pollInterval);
                } else {
                  console.log('[DocumentsTab] Max polls reached, stopping');
                  appendLog('已达到最大轮询次数，请手动刷新');
                  await loadDocuments();
                  return; // Important: stop polling
                }
              };
              
              // Start polling
              setTimeout(pollUntilDeletable, 500);
          } else {
              const errorMsg = response.error?.message || 'Unknown error';
              appendLog(t('pages.knowledge.documents.errorStoppingDocument') + errorMsg);
              message.error({
                content: t('pages.knowledge.documents.errorStoppingDocument') + errorMsg,
                duration: 8,
                style: { maxWidth: '600px' }
              });
          }
        } catch (e: any) {
          const errorMsg = e?.message || String(e);
          appendLog(t('pages.knowledge.documents.errorStoppingDocument') + errorMsg);
          message.error({
            content: t('pages.knowledge.documents.errorStoppingDocument') + errorMsg,
            duration: 8,
            style: { maxWidth: '600px' }
          });
          
          console.log('[DocumentsTab] Stop error occurred, restoring normal polling...');
          setTimeout(async () => {
            await loadDocuments();
            const countsResponse = await get_ipc_api().lightragApi.getStatusCounts({ workspace: workspace || undefined });
            if (countsResponse.success && countsResponse.data) {
              const counts = countsResponse.data as any;
              setStatusCounts({
                all: counts.all || 0,
                PROCESSED: counts.processed || 0,
                PROCESSING: counts.processing || 0,
                PENDING: counts.pending || 0,
                FAILED: counts.failed || 0
              });
            }
          }, 3000);
        }
      }
    });
  };

  const handleDeleteDocument = (doc: Document) => {
    const title = t('pages.knowledge.documents.deleteDocument');
    
    const status = doc.status?.toUpperCase();
    const isPending = status === 'PENDING';
    const isProcessing = status === 'PROCESSING';

    let confirmContent = '';
    if (isPending) {
      confirmContent = t('pages.knowledge.documents.deletePendingConfirm', { filePath: doc.file_path });
    } else if (isProcessing) {
      confirmContent = t('pages.knowledge.documents.deleteProcessingConfirm', { filePath: doc.file_path });
    } else {
      confirmContent = t('pages.knowledge.documents.deleteDocumentConfirm', { filePath: doc.file_path });
    }

    modal.confirm({
      title: title,
      content: confirmContent,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: (isPending || isProcessing) ? { danger: true } : undefined,
      onOk: async () => {
        try {
          // If document is PROCESSING, cancel pipeline first
          if (isProcessing) {
            requestStopPendingBatches('删除前已停止后续批次提交，正在请求停止当前处理...');
            appendLog(t('pages.knowledge.documents.stoppingProcessingFirst', { filePath: doc.file_path }));
            
            try {
              await get_ipc_api().lightragApi.abortDocument({ id: doc.id, workspace: workspace || undefined });
              appendLog(t('pages.knowledge.documents.processingStoppedWaitingUpdate'));
              
              // Wait longer for the cancellation to take effect and document to be marked as FAILED
              await new Promise(resolve => setTimeout(resolve, 3000));
            } catch (e) {
              console.error('[DocumentsTab] Failed to cancel before delete:', e);
              appendLog(t('pages.knowledge.documents.warnStopFailedTryDelete'));
            }
          }
          
          // For PENDING documents, warn user but still try
          if (isPending) {
            appendLog(t('pages.knowledge.documents.warnPendingCannotDelete', { filePath: doc.file_path }));
          }
          
          appendLog(t('pages.knowledge.documents.deletingDocument', { filePath: doc.file_path }));
          // Pass 'id' as required by the updated backend handler
          const response = await get_ipc_api().lightragApi.deleteDocument({ id: doc.id, workspace: workspace || undefined });
          if (response.success) {
              // Deletion is background async, show initiated message
              appendLog('文档删除已启动，正在后台处理...');
              message.success({
                content: '文档删除已启动，将在后台完成',
                duration: 3
              });
              
              // Poll to verify deletion completion. Reads `documentsRef.current`
              // (kept in sync by loadDocuments) rather than the React `documents`
              // state captured by this closure — the snapshot would always
              // include the doc we're deleting and the user would see
              // "删除验证超时" 60 s after the server already removed it
              // (observed 2026-09-04 with doc-1cd4ce4e…f9f3e2).
              let pollCount = 0;
              const maxPolls = 20; // Max 60 seconds (20 * 3s)
              const pollInterval = 3000;

              const pollUntilDeleted = async () => {
                pollCount++;
                console.log(`[DocumentsTab] Deletion poll ${pollCount}/${maxPolls}`);

                await loadDocuments();

                try {
                  const countsResponse = await get_ipc_api().lightragApi.getStatusCounts({ workspace: workspace || undefined });
                  if (countsResponse.success && countsResponse.data) {
                    const counts = countsResponse.data as any;
                    const statusData = counts?.data?.status_counts || counts?.status_counts || {};
                    const normalizedCounts: Record<string, number> = {};
                    Object.keys(statusData).forEach(key => {
                      normalizedCounts[key.toUpperCase()] = statusData[key];
                    });
                    const processed = normalizedCounts.PROCESSED || 0;
                    const processing = normalizedCounts.PROCESSING || 0;
                    const pending = normalizedCounts.PENDING || 0;
                    const failed = normalizedCounts.FAILED || 0;
                    const all = processed + processing + pending + failed;
                    setStatusCounts({
                      all,
                      PROCESSED: processed,
                      PROCESSING: processing,
                      PENDING: pending,
                      FAILED: failed,
                    });
                  }
                } catch (e) {
                  console.error('[DocumentsTab] Failed to refresh status counts:', e);
                }

                const stillExists = documentsRef.current.some((d: Document) => d.id === doc.id);
                if (!stillExists) {
                  appendLog('✅ 文档删除完成');
                  message.success('文档已成功删除');
                  return;
                }
                if (pollCount < maxPolls) {
                  setTimeout(pollUntilDeleted, pollInterval);
                } else {
                  appendLog('⚠️ 删除验证超时，请手动刷新查看');
                  message.warning('删除验证超时，请刷新页面确认');
                }
              };

              // Start polling after 2 seconds
              setTimeout(pollUntilDeleted, 2000);
          } else {
              const errorMsg = response.error?.message || 'Unknown error';
              
              // Special handling for PENDING documents
              if (isPending && errorMsg.includes('Cannot delete')) {
                const specialMsg = t('pages.knowledge.documents.cannotDeletePendingSolution');
                appendLog(specialMsg);
                message.warning({
                  content: specialMsg,
                  duration: 15,
                  style: { maxWidth: '600px', whiteSpace: 'pre-line' }
                });
              } else {
                appendLog(t('pages.knowledge.documents.errorDeletingDocument') + errorMsg);
                message.error({
                  content: t('pages.knowledge.documents.errorDeletingDocument') + errorMsg,
                  duration: 8,
                  style: { maxWidth: '600px' }
                });
              }
              throw new Error(errorMsg);
          }
        } catch (e: any) {
          const errorMsg = e?.message || String(e);
          // Error already handled above for PENDING documents
          if (!isPending || !errorMsg.includes('Cannot delete')) {
            appendLog(t('pages.knowledge.documents.errorDeletingDocument') + errorMsg);
            message.error({
              content: t('pages.knowledge.documents.errorDeletingDocument') + errorMsg,
              duration: 8,
              style: { maxWidth: '600px' }
            });
          }
        }
      }
    });
  };

  /**
   * Re-ingest a document in place after the user has edited the file
   * on disk. Opens a file picker, then calls `lightrag.replaceDocument`
   * which will:
   *   1. delete every existing doc in the workspace whose basename
   *      matches the picked file
   *   2. upload the new version
   *
   * The match is by basename so the user can pick the new copy from
   * any folder (e.g. they edited it elsewhere and saved it back).
   */
  const handleReplaceDocument = async (doc: Document) => {
    try {
      const filters = [
        { name: 'All Supported', extensions: ['*'] },
      ];
      const sel = await get_ipc_api().executeRequest<any>(
        'fs.selectFiles',
        { multiple: false, filters },
        300000,
      );
      if (!sel?.success || !sel.data?.paths?.length) return;

      const newPath = sel.data.paths[0] as string;
      const newName = newPath.split(/[\\/]/).pop() || newPath;
      const oldName = (doc.file_path || '').split(/[\\/]/).pop() || doc.file_path;

      modal.confirm({
        title: t('pages.knowledge.documents.replaceDocument', 'Replace document'),
        content: (
          <div style={{ fontSize: 13, lineHeight: 1.6 }}>
            <div>{t(
              'pages.knowledge.documents.replaceDocumentConfirm',
              'This will delete all existing copies matching the filename and re-ingest the new version. Continue?',
            )}</div>
            <div style={{ marginTop: 8, opacity: 0.75 }}>
              <div><b>Old:</b> {oldName}</div>
              <div><b>New:</b> {newPath}</div>
              {newName.toLowerCase() !== (oldName || '').toLowerCase() && (
                <div style={{ color: token.colorWarning, marginTop: 6 }}>
                  ⚠️ Filenames differ — only matches by basename will be replaced.
                </div>
              )}
            </div>
          </div>
        ),
        okText: t('common.confirm', 'Confirm'),
        cancelText: t('common.cancel', 'Cancel'),
        onOk: async () => {
          try {
            appendLog(`Replacing "${oldName}" with "${newPath}"...`);
            const resp = await get_ipc_api().lightragApi.replaceDocument<{
              deleted_count: number;
              deleted_ids: string[];
              ingest: any;
            }>({
              path: newPath,
              workspace: workspace || undefined,
            });
            if (!resp.success) {
              const msg = resp.error?.message || 'Unknown error';
              appendLog(`❌ Replace failed: ${msg}`);
              message.error({ content: `Replace failed: ${msg}`, duration: 8 });
              return;
            }
            const data = resp.data || ({} as any);
            appendLog(
              `✅ Replace started: deleted ${data.deleted_count ?? 0} old copy/copies, uploaded new version. ` +
              `It will appear as PROCESSING shortly.`,
            );
            message.success(
              t(
                'pages.knowledge.documents.replaceDocumentStarted',
                'Replacement uploaded — old copies are being cleaned up in the background.',
              ),
            );
            // Give the backend a beat to register the new doc, then refresh.
            setTimeout(() => loadDocuments(true), 1500);
          } catch (e: any) {
            const msg = e?.message || String(e);
            appendLog(`❌ Replace error: ${msg}`);
            message.error({ content: `Replace error: ${msg}`, duration: 8 });
          }
        },
      });
    } catch (e: any) {
      const msg = e?.message || String(e);
      appendLog(`❌ Replace error: ${msg}`);
      message.error({ content: `Replace error: ${msg}`, duration: 8 });
    }
  };

  const getStatusColor = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'PROCESSED': return token.colorSuccess;
      case 'PARSING':
      case 'ANALYZING':
      case 'PROCESSING': return token.colorWarning;
      case 'PREPROCESSED': return token.colorInfo;
      case 'PENDING': return token.colorTextTertiary;
      case 'FAILED': return token.colorError;
      default: return token.colorText;
    }
  };

  const getStatusText = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'PROCESSED': return t('pages.knowledge.documents.completed');
      case 'PARSING': return t('pages.knowledge.documents.parsing');
      case 'ANALYZING': return t('pages.knowledge.documents.analyzing');
      case 'PROCESSING': return t('pages.knowledge.documents.processing');
      case 'PREPROCESSED': return t('pages.knowledge.documents.preprocessed');
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
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      {contextHolder}
      <div style={{ 
        padding: '16px 24px', 
        flex: 1,
        display: 'flex', 
        flexDirection: 'column', 
        gap: 12,
        background: token.colorBgLayout,
        overflow: 'auto'
      }} data-ec-scope="lightrag-ported">
      {/* Document Management header and actions */}
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        padding: '8px 0',
        marginBottom: 4,
        gap: 12,
        flexWrap: 'wrap'
      }}>
        <div style={{ flex: '1 1 auto', minWidth: 0 }}>
          <h3 style={{ 
            margin: 0, 
            fontSize: 14, 
            fontWeight: 600, 
            color: token.colorText,
            lineHeight: 1.2,
            whiteSpace: 'nowrap'
          }}>
            {t('pages.knowledge.documents.title')}
          </h3>
          <p style={{ 
            margin: '4px 0 0 0', 
            fontSize: 13, 
            color: token.colorTextSecondary,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}>
            {t('pages.knowledge.documents.subtitle')}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', flexShrink: 0 }}>
          <button className="ec-btn" onClick={handleSelectFiles}>
            <FolderOpenOutlined /> {t('pages.knowledge.documents.uploadFiles')}
          </button>
          <button className="ec-btn" onClick={handleSelectDirectory}>
            <FolderOpenOutlined /> {t('pages.knowledge.documents.importDirectory')}
          </button>
        </div>
      </div>

      {/* Processing Progress Bar */}
      {processingProgress && (processingProgress.processing_count > 0 || processingProgress.pending_count > 0) && (
        <div style={{
          background: token.colorBgContainer,
          borderRadius: 12,
          border: `1px solid ${token.colorBorder}`,
          padding: '16px',
          boxShadow: isDark ? '0 2px 8px rgba(0, 0, 0, 0.15)' : '0 2px 8px rgba(0, 0, 0, 0.06)'
        }}>
          <div style={{ marginBottom: 12 }}>
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              marginBottom: 8
            }}>
              <span style={{ 
                fontSize: 14, 
                fontWeight: 600, 
                color: token.colorText 
              }}>
                {t('pages.knowledge.documents.processingProgress')}
              </span>
              <span style={{ 
                fontSize: 13, 
                color: token.colorTextSecondary 
              }}>
                {processingProgress.processed_count} / {processingProgress.total_count} {t('pages.knowledge.documents.documentsProcessed')}
              </span>
            </div>
            <Progress 
              percent={processingProgress.progress_percentage} 
              status="active"
              strokeColor={{
                from: token.colorPrimary,
                to: token.colorPrimaryActive,
              }}
            />
          </div>
          <div style={{ 
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 16,
            fontSize: 12,
            color: token.colorTextSecondary
          }}>
            <div style={{ display: 'flex', gap: 16 }}>
              <span>⏳ {t('pages.knowledge.documents.processing')}: {processingProgress.processing_count}</span>
              <span>📋 {t('pages.knowledge.documents.pending')}: {processingProgress.pending_count}</span>
              {processingProgress.failed_count > 0 && (
                <span style={{ color: token.colorError }}>❌ {t('pages.knowledge.documents.failed')}: {processingProgress.failed_count}</span>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Switch 
                size="small"
                checked={autoStopOnFailure}
                onChange={setAutoStopOnFailure}
              />
              <span style={{ fontSize: 12, color: token.colorTextSecondary }}>
                失败时自动停止
              </span>
            </div>
          </div>
        </div>
      )}

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
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between', 
          marginBottom: 8,
          paddingBottom: 8,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          flexShrink: 0
        }}>
          <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: token.colorText }}>{t('pages.knowledge.documents.uploadedDocuments')}</h4>
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
              size="small"
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
          flex: 1,
          minHeight: 300,
          border: `1px solid ${token.colorBorder}`, 
          borderRadius: 12, 
          background: token.colorBgContainer,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
        }}>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '2fr 1.5fr 110px 80px 80px 130px 130px 120px',
            gap: 8,
            padding: '6px 16px',
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
              <div style={{ fontWeight: 600, fontSize: 13 }}>{t('pages.knowledge.documents.noDocuments')}</div>
              <div style={{ fontSize: 13 }}>{t('pages.knowledge.documents.noDocumentsDesc')}</div>
            </div>
          ) : (
            <div style={{ flex: 1 }}>
              {documents.map((doc, idx) => (
                <div key={doc.id || doc.file_path || idx} style={{ 
                  display: 'grid', 
                  gridTemplateColumns: '2fr 1.5fr 110px 80px 80px 130px 130px 120px',
                  gap: 8,
                  padding: '6px 16px',
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
                  }} title={doc.file_path || `ID: ${doc.id}`}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {doc.file_path ? getFileIcon(doc.file_path) + ' ' + getFileName(doc.file_path) : '📄 (Unknown file)'}
                    </span>
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
                    {(['PARSING', 'ANALYZING', 'PROCESSING', 'PENDING'].includes(doc.status?.toUpperCase())) ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'center' }}>
                        <span style={{ fontSize: 11 }}>{getStatusText(doc.status)}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          {(() => {
                            const chunkProgress = parseLatestChunkProgress(processingProgress?.pipeline?.latest_message);
                            const isCurrentDoc = chunkProgress != null && doc.id === chunkProgress.docId;
                            const hasChunkProgress = isCurrentDoc;
                            const totalChunks = chunkProgress?.total ?? 0;
                            const processedChunks = chunkProgress?.current ?? 0;

                            return (
                              <>
                                <Progress
                                  percent={
                                    hasChunkProgress
                                      ? Math.round(processedChunks / totalChunks * 100)
                                      : (documentProgress.get(doc.id) ?? (doc.status?.toUpperCase() === 'PROCESSING' ? 25 : 5))
                                  }
                                  size="small"
                                  status="active"
                                  strokeColor={token.colorWarning}
                                  style={{ width: 60, margin: 0 }}
                                  showInfo={false}
                                />
                                {hasChunkProgress ? (
                                  <span style={{ fontSize: 10, color: token.colorTextSecondary, whiteSpace: 'nowrap' }}>
                                    {processedChunks}/{totalChunks}
                                  </span>
                                ) : null}
                              </>
                            );
                          })()}
                        </div>
                      </div>
                    ) : (
                      getStatusText(doc.status)
                    )}
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
                  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    {doc.status?.toUpperCase() === 'PROCESSING' ? (
                      <Tooltip title={t('pages.knowledge.documents.stopTooltip')}>
                        <button
                          type="button"
                          aria-label={t('pages.knowledge.documents.stop')}
                          onClick={() => handleAbortDocument(doc)}
                          style={{
                            width: 32,
                            height: 32,
                            padding: 0,
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: token.colorWarning,
                            background: token.colorWarningBg,
                            border: `1px solid ${token.colorWarningBorder}`,
                            borderRadius: 8,
                            cursor: 'pointer',
                            fontSize: 15,
                          }}
                        >
                          <StopOutlined />
                        </button>
                      </Tooltip>
                    ) : (
                      <div style={{
                        width: 96,
                        display: 'grid',
                        gridTemplateColumns: '32px 32px',
                        gap: 8,
                        justifyContent: 'center',
                        alignItems: 'center',
                      }}>
                        <Tooltip title={t('pages.knowledge.documents.replaceDocumentTooltip')}>
                          <button
                            type="button"
                            aria-label={t('pages.knowledge.documents.replaceDocument')}
                            onClick={() => handleReplaceDocument(doc)}
                            style={{
                              width: 32,
                              height: 32,
                              padding: 0,
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: token.colorPrimary,
                              background: token.colorPrimaryBg,
                              border: `1px solid ${token.colorPrimaryBorder}`,
                              borderRadius: 8,
                              cursor: 'pointer',
                              fontSize: 15,
                            }}
                          >
                            <UploadOutlined />
                          </button>
                        </Tooltip>
                        <Tooltip title={t('pages.knowledge.documents.deleteDocumentTooltip')}>
                          <button
                            type="button"
                            aria-label={t('pages.knowledge.documents.deleteDocument')}
                            onClick={() => handleDeleteDocument(doc)}
                            style={{
                              width: 32,
                              height: 32,
                              padding: 0,
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: token.colorError,
                              background: token.colorErrorBg,
                              border: `1px solid ${token.colorErrorBorder}`,
                              borderRadius: 8,
                              cursor: 'pointer',
                              fontSize: 15,
                            }}
                          >
                            <DeleteOutlined />
                          </button>
                        </Tooltip>
                      </div>
                    )}
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
        borderRadius: 12, 
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
          background: isDark ? token.colorBgTextHover : token.colorBgLayout,
          cursor: 'pointer'
        }}
        onClick={() => setConsoleCollapsed(!consoleCollapsed)}
        >
          <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: token.colorText, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ transform: consoleCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)', transition: 'transform 0.2s', display: 'inline-block' }}>▼</span>
            {t('pages.knowledge.documents.console', '控制台')}
          </h4>
          <button 
            className="ec-btn-small" 
            onClick={(e) => { e.stopPropagation(); handleClearLog(); }} 
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
        {!consoleCollapsed && (
        <div ref={consoleRef} style={{ 
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
        )}
      </div>

      {/* Scoped styles — button styles are owned by styles/lightragTheme.css */}
      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-btn-primary {
          background: ${token.colorPrimary};
          color: #ffffff;
          border-color: ${token.colorPrimary};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary:hover {
          background: ${token.colorPrimaryHover};
          border-color: ${token.colorPrimaryHover};
          color: #ffffff;
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:hover {
          border-color: ${token.colorPrimary};
          color: ${token.colorPrimary};
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
