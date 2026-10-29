// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "WorkLog",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "WorkLogCore"),
        // XCTest and swift-testing are unavailable with only the Command Line Tools, so checks run as an executable.
        .executableTarget(name: "WorkLogChecks", dependencies: ["WorkLogCore"]),
        .executableTarget(name: "WorkLog", dependencies: ["WorkLogCore"]),
    ]
)
