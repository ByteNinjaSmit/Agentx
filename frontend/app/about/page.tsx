"use client";

import { Brain, Network, ShieldCheck, Route, Database, Lightbulb, ArrowRight, ArrowDown } from "lucide-react";
import Link from "next/link";

export default function AboutPage() {
  return (
    <div className="max-w-5xl mx-auto pb-24 animate-slide-up">
      
      {/* Hero */}
      <div className="text-center py-16 mb-12 border-b border-[var(--border)]">
        <div className="inline-block px-3 py-1 bg-[var(--surface-2)] text-[var(--foreground-secondary)] text-xs font-bold tracking-widest uppercase rounded border border-[var(--border)] mb-6">
          Autonomous Research & Competitive Intelligence
        </div>
        <h1 className="text-4xl md:text-5xl font-semibold text-[var(--foreground)] mb-6 tracking-tight">
          Intelligence that investigates itself.
        </h1>
        <p className="text-xl text-[var(--foreground-secondary)] max-w-3xl mx-auto leading-relaxed">
          AgentX autonomously researches scientific developments, patents, competitors, news and industry signals — then determines what matters.
        </p>
      </div>

      {/* Visual Diagram */}
      <div className="mb-24 flex flex-col items-center">
        <div className="text-center font-mono text-sm mb-4">USER GOAL</div>
        <ArrowDown className="w-5 h-5 text-[var(--border-highlight)] mb-4" />
        
        <div className="surface-card px-8 py-3 font-semibold mb-4 border-[var(--accent)] text-[var(--accent)]">
          AUTONOMOUS PLANNER
        </div>
        <ArrowDown className="w-5 h-5 text-[var(--border-highlight)] mb-4" />

        <div className="flex gap-4 md:gap-12 mb-4">
          <div className="surface-card px-6 py-4 text-center">
            <div className="font-medium text-sm">Research Agent</div>
          </div>
          <div className="surface-card px-6 py-4 text-center">
            <div className="font-medium text-sm">Patent Agent</div>
          </div>
          <div className="surface-card px-6 py-4 text-center">
            <div className="font-medium text-sm">Competitor Agent</div>
          </div>
        </div>

        <ArrowDown className="w-5 h-5 text-[var(--border-highlight)] mb-4" />
        <div className="surface-card px-8 py-3 font-semibold mb-4">VERIFICATION</div>
        
        <ArrowDown className="w-5 h-5 text-[var(--border-highlight)] mb-4" />
        <div className="surface-card px-8 py-3 font-semibold mb-4">ANALYSIS</div>

        <ArrowDown className="w-5 h-5 text-[var(--border-highlight)] mb-4" />
        <div className="surface-card px-8 py-3 font-semibold mb-4">STRATEGY</div>

        <ArrowDown className="w-5 h-5 text-[var(--border-highlight)] mb-4" />
        <div className="px-8 py-3 bg-[var(--foreground)] text-[var(--surface)] rounded-lg font-bold tracking-wide">
          ACTIONABLE INSIGHT
        </div>
      </div>

      {/* Features Grid */}
      <div className="mb-24">
        <h2 className="text-2xl font-semibold text-center mb-12">What Makes AgentX Different?</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="surface-card p-6">
            <Brain className="w-6 h-6 text-[var(--accent)] mb-4" />
            <h3 className="font-semibold mb-2">Autonomous Reasoning</h3>
            <p className="text-sm text-[var(--foreground-secondary)]">AgentX decides what information it needs and what action to take next.</p>
          </div>
          <div className="surface-card p-6">
            <Network className="w-6 h-6 text-[var(--accent)] mb-4" />
            <h3 className="font-semibold mb-2">Multi-Agent Collaboration</h3>
            <p className="text-sm text-[var(--foreground-secondary)]">Specialized agents independently investigate different aspects of a problem.</p>
          </div>
          <div className="surface-card p-6">
            <ShieldCheck className="w-6 h-6 text-[var(--accent)] mb-4" />
            <h3 className="font-semibold mb-2">Evidence Verification</h3>
            <p className="text-sm text-[var(--foreground-secondary)]">Important findings are verified against the underlying source evidence.</p>
          </div>
          <div className="surface-card p-6">
            <Route className="w-6 h-6 text-[var(--accent)] mb-4" />
            <h3 className="font-semibold mb-2">Adaptive Planning</h3>
            <p className="text-sm text-[var(--foreground-secondary)]">The investigation can change direction when new information is discovered.</p>
          </div>
          <div className="surface-card p-6">
            <Database className="w-6 h-6 text-[var(--accent)] mb-4" />
            <h3 className="font-semibold mb-2">Persistent Memory</h3>
            <p className="text-sm text-[var(--foreground-secondary)]">Previous investigations and findings can influence future analysis.</p>
          </div>
          <div className="surface-card p-6">
            <Lightbulb className="w-6 h-6 text-[var(--accent)] mb-4" />
            <h3 className="font-semibold mb-2">Actionable Intelligence</h3>
            <p className="text-sm text-[var(--foreground-secondary)]">AgentX prioritizes important developments and converts them into strategic recommendations.</p>
          </div>
        </div>
      </div>

      {/* Advanced Agent Orchestration */}
      <div className="mb-24 surface-card p-10 bg-[var(--surface-2)]">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div>
            <h2 className="text-2xl font-semibold mb-4">Autonomous Runtime</h2>
            <p className="text-[var(--foreground-secondary)] mb-6">
              AgentX uses an agentic framework to orchestrate stateful, multi-agent investigations rather than executing a fixed sequence of AI calls. AgentX can change its investigation strategy when evidence, uncertainty, or execution conditions change.
            </p>
          </div>
          <div className="font-mono text-sm space-y-3 bg-[var(--surface)] p-6 rounded-lg border border-[var(--border)] shadow-sm">
            <div className="flex justify-between items-center"><span className="text-[var(--foreground)]">Dynamic Planning</span><span className="text-[var(--accent)]">✓</span></div>
            <div className="flex justify-between items-center"><span className="text-[var(--foreground)]">Conditional Routing</span><span className="text-[var(--accent)]">✓</span></div>
            <div className="flex justify-between items-center"><span className="text-[var(--foreground)]">Parallel Agents</span><span className="text-[var(--accent)]">✓</span></div>
            <div className="flex justify-between items-center"><span className="text-[var(--foreground)]">Shared State</span><span className="text-[var(--accent)]">✓</span></div>
            <div className="flex justify-between items-center"><span className="text-[var(--foreground)]">Replanning</span><span className="text-[var(--accent)]">✓</span></div>
            <div className="flex justify-between items-center"><span className="text-[var(--foreground)]">Failure Recovery</span><span className="text-[var(--accent)]">✓</span></div>
            <div className="flex justify-between items-center"><span className="text-[var(--foreground)]">Evidence Verification</span><span className="text-[var(--accent)]">✓</span></div>
            <div className="flex justify-between items-center"><span className="text-[var(--foreground)]">Persistent Checkpoints</span><span className="text-[var(--accent)]">✓</span></div>
          </div>
        </div>
      </div>

      {/* Comparison */}
      <div className="mb-24">
        <h2 className="text-center text-xl font-medium text-[var(--foreground-secondary)] mb-12">Not Just Another AI Chatbot</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs text-center">
          
          <div className="surface-card p-4">
            <h4 className="font-semibold text-sm mb-4 font-sans text-[var(--foreground)]">Traditional AI</h4>
            <div className="text-[var(--foreground-secondary)]">Question<br/>↓<br/>Answer</div>
          </div>
          
          <div className="surface-card p-4">
            <h4 className="font-semibold text-sm mb-4 font-sans text-[var(--foreground)]">Search Engine</h4>
            <div className="text-[var(--foreground-secondary)]">Query<br/>↓<br/>Results</div>
          </div>
          
          <div className="surface-card p-4">
            <h4 className="font-semibold text-sm mb-4 font-sans text-[var(--foreground)]">RAG</h4>
            <div className="text-[var(--foreground-secondary)]">Question<br/>↓<br/>Retrieve<br/>↓<br/>Generate</div>
          </div>
          
          <div className="surface-card p-4 border-[var(--accent)] bg-[rgba(49,85,212,0.03)]">
            <h4 className="font-semibold text-sm mb-4 font-sans text-[var(--accent)]">AgentX</h4>
            <div className="text-[var(--accent)] font-medium">Goal<br/>↓<br/>Plan<br/>↓<br/>Investigate<br/>↓<br/>Delegate<br/>↓<br/>Observe<br/>↓<br/>Verify<br/>↓<br/>Replan<br/>↓<br/>Remember<br/>↓<br/>Evaluate<br/>↓<br/>Recommend</div>
          </div>

        </div>
      </div>

      {/* CTA */}
      <div className="text-center p-12 surface-card bg-[var(--foreground)] text-[var(--surface)]">
        <h2 className="text-2xl font-semibold mb-2">Don&apos;t just monitor the world. Understand what changed.</h2>
        <p className="text-[var(--border-highlight)] mb-8">Turn emerging signals into action.</p>
        <Link href="/" className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--surface)] text-[var(--foreground)] font-semibold rounded-lg hover:bg-[var(--surface-2)] transition-colors">
          Start Investigation
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

    </div>
  );
}
