import { useState } from "react";
import axios from "axios";

export default function Home() {
  const [msg, setMsg] = useState("");
  const [reply, setReply] = useState("");

  const send = async () => {
    const res = await axios.post(
      process.env.NEXT_PUBLIC_MCP_URL + "/chat",
      { message: msg }
    );
    setReply(res.data.reply);
  };

  return (
    <div style={{ padding: 40, fontFamily: "Arial" }}>
      <h1>MCP AI Chat</h1>

      <textarea
        rows={4}
        style={{ width: "100%" }}
        value={msg}
        onChange={(e) => setMsg(e.target.value)}
      />

      <br /><br />

      <button onClick={send}>Send</button>

      <pre style={{ marginTop: 20 }}>{reply}</pre>
    </div>
  );
}