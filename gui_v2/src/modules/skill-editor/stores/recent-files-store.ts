/**
 * Recent Files Store
 * Manages recently opened skill files with persistence
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { hasFullFilePaths } from '../../../config/platform';

export interface RecentFile {
  filePath: string;
  fileName: string;
  lastOpened: string; // ISO date string
  skillName?: string;
}

interface RecentFilesState {
  recentFiles: RecentFile[];
  maxRecentFiles: number;
}

interface RecentFilesActions {
  addRecentFile: (file: RecentFile) => void;
  removeRecentFile: (filePath: string) => void;
  clearRecentFiles: () => void;
  getMostRecentFile: () => RecentFile | null;
  getRecentFiles: () => RecentFile[];
}

type RecentFilesStore = RecentFilesState & RecentFilesActions;

const MAX_RECENT_FILES = 10;

export const useRecentFilesStore = create<RecentFilesStore>()(
  persist(
    (set, get) => ({
      recentFiles: [],
      maxRecentFiles: MAX_RECENT_FILES,

      addRecentFile: (file: RecentFile) => {
        // Only track recent files if we have full file path support (desktop mode)
        if (!hasFullFilePaths()) {
          return;
        }

        set((state) => {
          const existingIndex = state.recentFiles.findIndex(
            (rf) => rf.filePath === file.filePath
          );

          let updatedFiles = [...state.recentFiles];

          if (existingIndex >= 0) {
            // Update existing file's last opened time and move to front
            updatedFiles[existingIndex] = {
              ...updatedFiles[existingIndex],
              ...file,
              lastOpened: new Date().toISOString(),
            };
            // Move to front
            const updatedFile = updatedFiles.splice(existingIndex, 1)[0];
            updatedFiles.unshift(updatedFile);
          } else {
            // Add new file to front
            const newFile = {
              ...file,
              lastOpened: new Date().toISOString(),
            };
            updatedFiles.unshift(newFile);
          }

          // Keep only the most recent files
          if (updatedFiles.length > state.maxRecentFiles) {
            updatedFiles = updatedFiles.slice(0, state.maxRecentFiles);
          }

          return {
            recentFiles: updatedFiles,
          };
        });
      },

      removeRecentFile: (filePath: string) => {
        set((state) => ({
          recentFiles: state.recentFiles.filter((rf) => rf.filePath !== filePath),
        }));
      },

      clearRecentFiles: () => {
        set({ recentFiles: [] });
      },

      getMostRecentFile: (): RecentFile | null => {
        const { recentFiles } = get();
        return recentFiles.length > 0 ? recentFiles[0] : null;
      },

      getRecentFiles: (): RecentFile[] => {
        const { recentFiles } = get();
        return [...recentFiles]; // Return a copy
      },
    }),
    {
      name: 'skill-editor-recent-files', // localStorage key
      // Always hydrate - platform check is done in addRecentFile
    }
  )
);

/**
 * Utility function to extract file name from file path
 */
export function extractFileName(filePath: string): string {
  if (!filePath) return 'Unknown File';
  
  // Handle both Windows and Unix path separators
  const parts = filePath.replace(/\\/g, '/').split('/');
  return parts[parts.length - 1] || 'Unknown File';
}

/**
 * Utility function to create a RecentFile object from file path and skill info
 */
export function createRecentFile(
  filePath: string, 
  skillName?: string
): RecentFile {
  return {
    filePath,
    fileName: extractFileName(filePath),
    lastOpened: new Date().toISOString(),
    skillName,
  };
}
