"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search, ArrowRight, Activity, Cpu, Lightbulb } from "lucide-react";

export default function Home() {
  const [query, setQuery] = useState("");
  const router = useRouter();

  const handleInvestigate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    // The goal travels in the query string; /investigate/new starts the real
    // agent run (backend SSE or n8n webhook, per the operator's saved settings)
    // against it.
    router.push(`/investigate/new?goal=${encodeURIComponent(query.trim())}`);
  };

  const suggestions = [
    { icon: <Activity className="w-4 h-4 text-[var(--accent)]" />, text: "Competitor activity" },
    { icon: <Lightbulb className="w-4 h-4 text-[var(--warning)]" />, text: "Patent trends" },
    { icon: <Cpu className="w-4 h-4 text-[var(--accent-secondary)]" />, text: "Research trends" },
  ];

  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] max-w-3xl mx-auto px-4">
      
      <div className="text-center mb-10 animate-slide-up">
        <h1 className="text-3xl font-semibold text-[var(--foreground)] mb-2">
          Good evening. What should AgentX investigate?
        </h1>
        <p className="text-[var(--foreground-secondary)]">
          Autonomous intelligence gathering across research, patents, and competitors.
        </p>
      </div>

      <form 
        onSubmit={handleInvestigate} 
        className="w-full surface-card p-2 mb-8 animate-slide-up"
        style={{ animationDelay: "100ms" }}
      >
        <div className="relative flex items-center">
          <Search className="absolute left-4 w-5 h-5 text-[var(--foreground-secondary)]" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Analyze emerging competitors in generative AI infrastructure..."
            className="w-full pl-12 pr-32 py-4 bg-transparent border-none focus:outline-none text-lg text-[var(--foreground)] placeholder:text-[var(--border-highlight)]"
          />
          <button
            type="submit"
            className="absolute right-2 px-4 py-2 bg-[var(--foreground)] text-[var(--surface)] font-medium rounded-lg hover:bg-[var(--accent)] transition-colors flex items-center gap-2"
          >
            Investigate
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>

      <div className="w-full mb-16 animate-slide-up" style={{ animationDelay: "200ms" }}>
        <p className="text-sm font-medium text-[var(--foreground-secondary)] mb-4 pl-1">Suggested investigations</p>
        <div className="flex flex-wrap gap-3">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onClick={() => setQuery(s.text)}
              className="flex items-center gap-2 px-4 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-full text-sm font-medium hover:border-[var(--border-highlight)] hover:shadow-[var(--shadow-sm)] transition-all"
            >
              {s.icon}
              {s.text}
            </button>
          ))}
        </div>
      </div>

      <div className="w-full p-6 surface-card animate-slide-up" style={{ animationDelay: "300ms" }}>
        <h3 className="text-sm font-semibold mb-4 text-[var(--foreground)] flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[var(--accent)]"></div>
          Autonomous Investigation Process
        </h3>
        <p className="text-[var(--foreground-secondary)] text-sm leading-relaxed">
          AgentX will automatically:<br/>
          <span className="font-mono text-xs mt-2 block space-y-1 text-[var(--foreground)]">
            <span className="text-[var(--foreground-secondary)]">01</span> Plan the investigation<br/>
            <span className="text-[var(--foreground-secondary)]">02</span> Select appropriate sources<br/>
            <span className="text-[var(--foreground-secondary)]">03</span> Delegate specialist tasks<br/>
            <span className="text-[var(--foreground-secondary)]">04</span> Verify evidence<br/>
            <span className="text-[var(--foreground-secondary)]">05</span> Analyze findings<br/>
            <span className="text-[var(--foreground-secondary)]">06</span> Generate strategic recommendations
          </span>
        </p>
      </div>

    </div>
  );
}
