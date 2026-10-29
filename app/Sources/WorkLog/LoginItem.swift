import Foundation
import ServiceManagement

enum LoginItem {
    private static let firstLaunchDoneKey = "loginItemFirstLaunchDone"

    // Only the first launch follows the setting on its own; later the user's choice in System Settings is left alone.
    static func applyOnFirstLaunch(_ enabled: Bool) {
        guard AppEnvironment.isBundled else { return apply(enabled) }
        let defaults = UserDefaults.standard
        guard !defaults.bool(forKey: firstLaunchDoneKey) else { return }
        apply(enabled)
        defaults.set(true, forKey: firstLaunchDoneKey)
    }

    static func apply(_ enabled: Bool) {
        guard AppEnvironment.isBundled else {
            AppEnvironment.log("no app bundle, launch at login \(enabled ? "register" : "unregister") skipped")
            return
        }
        let service = SMAppService.mainApp
        do {
            if enabled, service.status != .enabled {
                try service.register()
            } else if !enabled, service.status == .enabled {
                try service.unregister()
            }
        } catch {
            AppEnvironment.log("launch at login change failed: \(error.localizedDescription)")
        }
    }
}
