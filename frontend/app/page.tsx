import Link from "next/link";

export default function HomePage() {
  return <>
    <section className="card welcome">
      <div className="eyebrow">LLM SERVING PLATFORM</div>
      <h1>From a question<br />to a real model response.</h1>
      <p>A small, working inference platform. Start with Chat; open Admin when you want to manage model metadata or inspect the gateway.</p>
      <Link className="btn" href="/chat">Open Chat →</Link>
    </section>
    <div className="grid cols-2eq">
      <Link className="card start-card" href="/chat"><span className="eyebrow">01 / TRY IT</span><h2>Talk to the model</h2><p>Type a question and send. The default backend and model are already configured.</p><strong>Start a conversation →</strong></Link>
      <Link className="card start-card" href="/admin"><span className="eyebrow">02 / OPERATE IT</span><h2>Manage and inspect</h2><p>Register a version, update its stage, or inspect routing and response-cache statistics.</p><strong>Open Admin →</strong></Link>
    </div>
    <section className="card"><h2>What happens behind the scenes?</h2><p className="flow-line">Browser → API gateway → GPU inference → Streamed answer</p><p className="sub">The gateway handles routing and response caching. Ray Serve and vLLM run the model on a rented GPU. A deployed website does not imply that the GPU is always online.</p><a href="https://github.com/xiyiji/llm-serving-platform">Read the architecture and test evidence on GitHub ↗</a></section>
  </>;
}
