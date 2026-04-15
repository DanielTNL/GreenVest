import XCTest

final class GreenVestUITests: XCTestCase {
    func testTabNavigationAndChatButton() {
        let app = XCUIApplication()
        app.launchArguments.append("UI_TEST_MODE")
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["Stocks"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.tabBars.buttons["Simulations"].exists)
        XCTAssertTrue(app.tabBars.buttons["Metrics"].exists)
        XCTAssertTrue(app.tabBars.buttons["Macro"].exists)
        XCTAssertTrue(app.tabBars.buttons["Alerts"].exists)

        app.tabBars.buttons["Simulations"].tap()
        XCTAssertTrue(app.buttons["Run Weekly Simulation"].waitForExistence(timeout: 5))

        app.buttons["floating_chat_button"].tap()
        XCTAssertTrue(app.navigationBars["Assistant"].waitForExistence(timeout: 5))
    }
}
