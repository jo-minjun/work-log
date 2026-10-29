import Foundation

nonisolated(unsafe) var passedCount = 0
nonisolated(unsafe) var failedCount = 0

func check(_ condition: Bool, _ name: String) {
    if condition {
        passedCount += 1
        print("PASS \(name)")
    } else {
        failedCount += 1
        print("FAIL \(name)")
    }
}
