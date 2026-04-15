import Foundation
import SwiftUI

enum AppTheme {
    static let backgroundGradient = LinearGradient(
        colors: [
            Color.gvBackground.opacity(0.95),
            Color.gvAccent.opacity(0.12),
            Color.gvBackground
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
}

extension Color {
    static let gvAccent = Color("AppAccent")
    static let gvBackground = Color("AppBackground")
    static let gvCardBackground = Color("CardBackground")
    static let gvChartPositive = Color("ChartPositive")
    static let gvChartNegative = Color("ChartNegative")
}

enum FinancialFormatters {
    static let currency: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.maximumFractionDigits = 2
        return formatter
    }()

    static let percent: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .percent
        formatter.maximumFractionDigits = 2
        return formatter
    }()

    static let decimal: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 3
        return formatter
    }()
}

extension Double {
    var currencyString: String {
        FinancialFormatters.currency.string(from: NSNumber(value: self)) ?? "$\(self)"
    }

    var percentString: String {
        FinancialFormatters.percent.string(from: NSNumber(value: self)) ?? "\(self * 100)%"
    }

    var decimalString: String {
        FinancialFormatters.decimal.string(from: NSNumber(value: self)) ?? "\(self)"
    }
}

enum AppDateParser {
    static let iso8601: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    static let fallbackISO8601: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static let shortDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        return formatter
    }()

    static func parse(_ value: String?) -> Date {
        guard let value else { return .now }
        if let date = iso8601.date(from: value) ?? fallbackISO8601.date(from: value) {
            return date
        }
        return ISO8601DateFormatter().date(from: "\(value)T00:00:00Z") ?? .now
    }
}
