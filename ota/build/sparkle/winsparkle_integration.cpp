#include <windows.h>
#include "winsparkle.h"

// ECBot winSparkle集成
class ECBotWinSparkleUpdater {
public:
    ECBotWinSparkleUpdater() {
        // 初始化winSparkle
        win_sparkle_set_appcast_url(L"https://your-server.com/appcast.xml");
        win_sparkle_set_app_details(L"ECBot", L"ECBot", L"1.0.0");
        win_sparkle_init();
    }
    
    ~ECBotWinSparkleUpdater() {
        win_sparkle_cleanup();
    }
    
    void checkForUpdates() {
        win_sparkle_check_update_with_ui();
    }
    
    void checkForUpdatesInBackground() {
        win_sparkle_check_update_without_ui();
    }
};
