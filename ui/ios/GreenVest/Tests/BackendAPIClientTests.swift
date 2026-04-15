import Foundation
import XCTest
@testable import GreenVest

final class BackendAPIClientTests: XCTestCase {
    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        super.tearDown()
    }

    func testFetchStocksDecodesItems() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)

        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8000/api/stocks")
            let payload = """
            {"items":[{"symbol":"AAPL","name":"Apple Inc.","exchange":"NASDAQ","asset_type":"equity","source":"test","latest_close":201.42,"latest_price_timestamp_utc":"2026-04-14T16:00:00+00:00"}]}
            """
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(payload.utf8))
        }

        let client = BackendAPIClient(
            session: session,
            baseURLProvider: { URL(string: "http://127.0.0.1:8000/api") }
        )

        let stocks = try await client.fetchStocks(query: nil)
        XCTAssertEqual(stocks.count, 1)
        XCTAssertEqual(stocks.first?.symbol, "AAPL")
        XCTAssertEqual(stocks.first?.latestClose, 201.42)
    }
}

final class MockURLProtocol: URLProtocol {
    static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.requestHandler else {
            XCTFail("Request handler missing.")
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
