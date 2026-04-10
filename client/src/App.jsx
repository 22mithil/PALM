import ChatTest from "./components/ChatTest"
import WebcamCapture from "./components/WebcamCapture"

function App() {
  return (
    <div className="dark" style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "2rem",
      background: "oklch(0.13 0.01 260)",
    }}>
      <WebcamCapture />
      {/* <ChatTest /> */}
    </div>
  )
}

export default App