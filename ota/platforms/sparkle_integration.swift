import Foundation
import Sparkle

@objc class SparkleManager: NSObject {
    static let shared = SparkleManager()
    private var updater: SPUUpdater?
    
    override init() {
        super.init()
        setupSparkle()
    }
    
    private func setupSparkle() {
        // 创建Sparkle配置
        let hostBundle = Bundle.main
        let driver = SPUStandardUserDriver(hostBundle: hostBundle, delegate: nil)
        
        // 设置更新服务器URL
        let feedURL = URL(string: "https://updates.ecbot.com/appcast.xml")!
        
        // 创建更新器
        updater = SPUUpdater(hostBundle: hostBundle, applicationBundle: hostBundle, userDriver: driver, delegate: nil)
        
        // 设置feed URL
        updater?.feedURL = feedURL
        
        // 配置更新器
        updater?.automaticallyChecksForUpdates = true
        updater?.automaticallyDownloadsUpdates = false
        updater?.checkInterval = 3600 // 1小时检查一次
    }
    
    @objc func checkForUpdates() {
        updater?.checkForUpdates(nil)
    }
    
    @objc func checkForUpdatesInBackground() {
        updater?.checkForUpdatesInBackground()
    }
    
    @objc func installUpdate() {
        updater?.installUpdatesIfAvailable()
    }
    
    @objc func setAutomaticallyChecksForUpdates(_ enabled: Bool) {
        updater?.automaticallyChecksForUpdates = enabled
    }
    
    @objc func setAutomaticallyDownloadsUpdates(_ enabled: Bool) {
        updater?.automaticallyDownloadsUpdates = enabled
    }
    
    @objc func getLastUpdateCheckDate() -> Date? {
        return updater?.lastUpdateCheckDate
    }
    
    @objc func isUpdateInProgress() -> Bool {
        return updater?.updateInProgress ?? false
    }
}

// 命令行接口
@objc class SparkleCLI: NSObject {
    static func main() {
        let manager = SparkleManager.shared
        
        // 解析命令行参数
        let args = CommandLine.arguments
        if args.count < 2 {
            print("Usage: sparkle-cli <command>")
            print("Commands: check, install, background")
            exit(1)
        }
        
        let command = args[1]
        
        switch command {
        case "check":
            manager.checkForUpdates()
        case "install":
            manager.installUpdate()
        case "background":
            manager.checkForUpdatesInBackground()
        default:
            print("Unknown command: \(command)")
            exit(1)
        }
    }
}

// 如果直接运行此文件
if CommandLine.arguments.contains("--cli") {
    SparkleCLI.main()
} 