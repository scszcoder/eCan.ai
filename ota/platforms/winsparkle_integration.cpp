#include <windows.h>
#include <winsparkle.h>
#include <iostream>
#include <string>

class WinSparkleManager {
private:
    static WinSparkleManager* instance;
    bool initialized;

    WinSparkleManager() : initialized(false) {
        initializeSparkle();
    }

    void initializeSparkle() {
        if (initialized) return;

        // 设置更新服务器URL
        win_sparkle_set_appcast_url("https://updates.ecbot.com/appcast.xml");
        
        // 设置应用程序信息
        win_sparkle_set_app_name("ECBot");
        win_sparkle_set_app_version("1.0.0");
        win_sparkle_set_company_name("ECBot Team");
        
        // 配置更新器
        win_sparkle_set_automatic_check_for_updates(1);
        win_sparkle_set_automatically_download_updates(0);
        win_sparkle_set_check_update_interval(3600); // 1小时
        
        // 初始化Sparkle
        win_sparkle_init();
        initialized = true;
    }

public:
    static WinSparkleManager* getInstance() {
        if (instance == nullptr) {
            instance = new WinSparkleManager();
        }
        return instance;
    }

    void checkForUpdates() {
        if (!initialized) return;
        win_sparkle_check_update_with_ui();
    }

    void checkForUpdatesInBackground() {
        if (!initialized) return;
        win_sparkle_check_update_without_ui();
    }

    void installUpdate() {
        if (!initialized) return;
        win_sparkle_install_update();
    }

    void setAutomaticChecks(bool enabled) {
        if (!initialized) return;
        win_sparkle_set_automatic_check_for_updates(enabled ? 1 : 0);
    }

    void setAutomaticDownloads(bool enabled) {
        if (!initialized) return;
        win_sparkle_set_automatically_download_updates(enabled ? 1 : 0);
    }

    bool isUpdateInProgress() {
        if (!initialized) return false;
        return win_sparkle_get_update_in_progress() != 0;
    }

    void cleanup() {
        if (initialized) {
            win_sparkle_cleanup();
            initialized = false;
        }
    }

    ~WinSparkleManager() {
        cleanup();
    }
};

WinSparkleManager* WinSparkleManager::instance = nullptr;

// 命令行接口
class WinSparkleCLI {
public:
    static int main(int argc, char* argv[]) {
        if (argc < 2) {
            std::cout << "Usage: winsparkle-cli.exe <command>" << std::endl;
            std::cout << "Commands: check, install, background" << std::endl;
            return 1;
        }

        std::string command = argv[1];
        WinSparkleManager* manager = WinSparkleManager::getInstance();

        if (command == "check") {
            manager->checkForUpdates();
        } else if (command == "install") {
            manager->installUpdate();
        } else if (command == "background") {
            manager->checkForUpdatesInBackground();
        } else {
            std::cout << "Unknown command: " << command << std::endl;
            return 1;
        }

        return 0;
    }
};

// DLL导出函数
extern "C" {
    __declspec(dllexport) void CheckForUpdates() {
        WinSparkleManager::getInstance()->checkForUpdates();
    }

    __declspec(dllexport) void CheckForUpdatesInBackground() {
        WinSparkleManager::getInstance()->checkForUpdatesInBackground();
    }

    __declspec(dllexport) void InstallUpdate() {
        WinSparkleManager::getInstance()->installUpdate();
    }

    __declspec(dllexport) void SetAutomaticChecks(int enabled) {
        WinSparkleManager::getInstance()->setAutomaticChecks(enabled != 0);
    }

    __declspec(dllexport) void SetAutomaticDownloads(int enabled) {
        WinSparkleManager::getInstance()->setAutomaticDownloads(enabled != 0);
    }

    __declspec(dllexport) int IsUpdateInProgress() {
        return WinSparkleManager::getInstance()->isUpdateInProgress() ? 1 : 0;
    }
}

// 主函数
int main(int argc, char* argv[]) {
    return WinSparkleCLI::main(argc, argv);
} 