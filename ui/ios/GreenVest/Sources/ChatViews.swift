import SwiftUI

struct ChatAssistantScreen: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: ChatViewModel

    init(backend: any BackendServing) {
        _viewModel = StateObject(wrappedValue: ChatViewModel(backend: backend))
    }

    var body: some View {
        NavigationStack {
            ScreenContainer {
                ScrollViewReader { proxy in
                    VStack(spacing: 0) {
                        ScrollView {
                            LazyVStack(spacing: 12) {
                                ForEach(viewModel.messages) { message in
                                    VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 8) {
                                        HStack {
                                            if message.role == .assistant { Spacer(minLength: 0) }
                                            Text(message.text)
                                                .padding(14)
                                                .frame(maxWidth: 300, alignment: message.role == .user ? .trailing : .leading)
                                                .background(
                                                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                                                        .fill(message.role == .user ? Color.gvAccent : Color.gvCardBackground)
                                                )
                                                .foregroundStyle(message.role == .user ? .white : .primary)
                                            if message.role == .user { Spacer(minLength: 0) }
                                        }
                                        if !message.actions.isEmpty {
                                            ScrollView(.horizontal, showsIndicators: false) {
                                                HStack {
                                                    ForEach(message.actions) { action in
                                                        Button(action.title) {
                                                            Task { await viewModel.send(message: action.prompt) }
                                                        }
                                                        .buttonStyle(.bordered)
                                                        .tint(.gvAccent)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    .id(message.id)
                                }
                                if viewModel.isSending {
                                    ProgressView()
                                        .tint(.gvAccent)
                                        .frame(maxWidth: .infinity)
                                }
                            }
                            .padding()
                        }

                        if let errorMessage = viewModel.errorMessage {
                            ErrorBanner(message: errorMessage)
                                .padding(.horizontal)
                                .padding(.bottom, 8)
                        }

                        Divider()
                        HStack(spacing: 12) {
                            TextField("Ask about risk, baskets, or simulations…", text: $viewModel.inputText, axis: .vertical)
                                .textFieldStyle(.roundedBorder)
                            Button {
                                Task { await viewModel.sendCurrentMessage() }
                            } label: {
                                Image(systemName: "arrow.up.circle.fill")
                                    .font(.system(size: 28))
                                    .foregroundStyle(Color.gvAccent)
                            }
                            .disabled(viewModel.isSending || viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                        .padding()
                    }
                    .onAppear {
                        if let lastMessageID = viewModel.messages.last?.id {
                            proxy.scrollTo(lastMessageID, anchor: .bottom)
                        }
                    }
                    .onChange(of: viewModel.messages.count) { _, _ in
                        guard let lastMessageID = viewModel.messages.last?.id else { return }
                        withAnimation(.easeOut(duration: 0.2)) {
                            proxy.scrollTo(lastMessageID, anchor: .bottom)
                        }
                    }
                }
            }
            .navigationTitle("Assistant")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
