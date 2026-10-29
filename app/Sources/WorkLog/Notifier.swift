import Foundation
import UserNotifications
import WorkLogCore

final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    private var center: UNUserNotificationCenter? {
        AppEnvironment.isBundled ? UNUserNotificationCenter.current() : nil
    }

    func requestAuthorization() {
        guard let center else {
            AppEnvironment.log("no app bundle, notifications are logged only")
            return
        }
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error { AppEnvironment.log("notification authorization failed: \(error.localizedDescription)") }
            else if !granted { AppEnvironment.log("notifications were not allowed") }
        }
    }

    func post(_ text: NotificationText) {
        guard let center else {
            AppEnvironment.log("notification: \(text.title)\(text.body.map { " - \($0)" } ?? "")")
            return
        }
        let content = UNMutableNotificationContent()
        content.title = text.title
        if let body = text.body { content.body = body }
        center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)) { error in
            if let error { AppEnvironment.log("notification failed: \(error.localizedDescription)") }
        }
    }

    // A menu bar app counts as frontmost while its window is open; without this the banner would be suppressed.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}
