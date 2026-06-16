import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  Bot,
  ChevronRight,
  Command,
  Cpu,
  History,
  MessageSquare,
  Send,
  ShieldCheck,
  Sparkles,
  User
} from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
import { safeEvidenceJson } from '../lib/redaction';
import type { AgentConfirmation, AgentRunResponse, RagStatus } from '../lib/types';

type Message = {
  role: 'user' | 'agent';
  content: string;
  response?: AgentRunResponse;
  timestamp: Date;
};

const SUGGESTIONS = [
  "Explain current task status and results",
  "What are the requirements for QSIRecon?",
  "Analyze the latest T1 result summary",
  "Recommend next steps for project review"
];

function dependencyAvailable(status: RagStatus | undefined, name: string) {
  const dependency = status?.dependencies?.[name];
  if (typeof dependency === 'boolean') return dependency;
  return Boolean(dependency?.available);
}

function formatEngine(engine: string | null | undefined) {
  if (!engine) return 'Not reported';
  const words = engine
    .split('_')
    .filter(Boolean)
    .join(' ');
  return words.charAt(0).toUpperCase() + words.slice(1).toLowerCase();
}

function agentMessageContent(data: AgentRunResponse) {
  if (data.status === 'task_created' && data.task?.id) {
    return `Task ${data.task.id} created for ${data.task.workflow_type}.`;
  }
  if (data.status === 'confirmation_required' && data.confirmation?.workflow_type) {
    return data.answer || `Approval required for ${data.confirmation.workflow_type}.`;
  }
  return data.answer || data.message || 'Agent run completed.';
}

export function AgentPage() {
  const projectId = Number(useParams().projectId);
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: status } = useQuery({
    queryFn: api.ragStatus,
    queryKey: queryKeys.ragStatus
  });
  const { data: deployment } = useQuery({
    queryFn: api.deployment,
    queryKey: queryKeys.deployment
  });
  const projectQuery = useQuery({
    enabled: Boolean(projectId),
    queryFn: () => api.listSeries(projectId),
    queryKey: queryKeys.series(projectId),
    retry: false,
  });

  const ask = useMutation({
    mutationFn: (message: string) => api.runAgent(projectId, message),
    onSuccess: (data) => {
      const agentMsg: Message = {
        role: 'agent',
        content: agentMessageContent(data),
        response: data,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, agentMsg]);
      if (data.status === 'task_created') {
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
        if (data.task?.id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task.id) });
        }
      }
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Agent run failed.';
      setMessages(prev => [...prev, { role: 'agent', content: message, timestamp: new Date() }]);
    }
  });

  const resume = useMutation({
    mutationFn: ({ approved, confirmation, threadId }: { approved: boolean; confirmation: AgentConfirmation; threadId: string }) =>
      api.resumeAgent(threadId, approved, confirmation),
    onSuccess: (data) => {
      const agentMsg: Message = {
        role: 'agent',
        content: agentMessageContent(data),
        response: data,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, agentMsg]);
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
      if (data.status === 'task_created' && data.task?.id) {
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task.id) });
      }
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Workflow approval failed.';
      setMessages(prev => [...prev, { role: 'agent', content: message, timestamp: new Date() }]);
    }
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim() || ask.isPending) return;

    const userMsg: Message = {
      role: 'user',
      content: query.trim(),
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMsg]);
    ask.mutate(query.trim());
    setQuery('');
  }

  const lastResponse = [...messages].reverse().find(m => m.response)?.response;
  const pendingConfirmation = lastResponse?.status === 'confirmation_required' && lastResponse.thread_id && lastResponse.confirmation
    ? { confirmation: lastResponse.confirmation, threadId: lastResponse.thread_id }
    : null;
  const semanticIndexReady = Boolean(status?.index?.semantic_index);
  const llamaIndexAvailable = dependencyAvailable(status, 'llama_index');
  const groundingLabel = semanticIndexReady ? 'Grounding Enabled' : 'Grounding Fallback';
  const retrievalLabel = semanticIndexReady ? 'Semantic Index' : 'Fallback Retrieval';
  const engineLabel = formatEngine(status?.index?.engine);
  const documentCount = status?.index?.document_count ?? 0;
  const chunkCount = status?.index?.chunk_count ?? 0;
  const modelGatewayConfigured = Boolean(deployment?.agent?.configured);
  const modelGatewayLabel = modelGatewayConfigured ? 'Configured' : 'Not configured';
  const modelGatewayDetail = deployment?.agent?.provider
    ? [deployment.agent.provider, deployment.agent.model].filter(Boolean).join(' / ')
    : 'Unavailable';
  const gatewayDiagnostics = deployment?.agent?.gateway_diagnostics;
  const sdkRoute = gatewayDiagnostics?.sdk_method || 'Not reported';
  const toolLoop = gatewayDiagnostics?.model_tool_loop || 'Not reported';
  const projectErrorMessage = projectQuery.error instanceof Error ? projectQuery.error.message : 'Project data could not be loaded.';

  if (projectQuery.isError) {
    return (
      <div className="max-w-7xl mx-auto space-y-8 px-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Bot className="w-6 h-6 text-[#065F46]" /> Agent Review
          </h1>
          <p className="text-xs text-gray-500 mt-1">Grounded analysis of project tasks, workflows, and scientific results.</p>
        </div>
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
          <div className="flex items-center gap-2 text-base font-semibold text-amber-900">
            <AlertCircle className="w-4 h-4 shrink-0" /> Project data unavailable
          </div>
          <p className="mt-2">{projectErrorMessage}</p>
          <Link
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-semibold text-amber-800 shadow-sm ring-1 ring-amber-200 hover:bg-amber-100"
            to="/projects"
          >
            Switch project
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto h-[calc(100vh-160px)] flex flex-col gap-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Bot className="w-6 h-6 text-[#065F46]" /> Agent Review
          </h1>
          <p className="text-xs text-gray-500 mt-1">Grounded analysis of project tasks, workflows, and scientific results.</p>
        </div>
        <div className="flex items-center gap-2">
           <div className="px-3 py-1.5 rounded-lg bg-white border border-gray-200 shadow-sm flex items-center gap-2 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
             {semanticIndexReady ? <ShieldCheck className="w-3.5 h-3.5 text-green-500" /> : <AlertCircle className="w-3.5 h-3.5 text-amber-500" />} {groundingLabel}
           </div>
        </div>
      </div>

      <div className="flex-1 flex gap-6 overflow-hidden">
        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden relative">
          {/* Chat History */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-6 space-y-6"
          >
            {messages.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center text-center space-y-6 px-12">
                <div className="w-16 h-16 rounded-2xl bg-[#ECFDF5] text-[#065F46] flex items-center justify-center">
                  <Sparkles className="w-8 h-8" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900">How can I assist your review?</h3>
                  <p className="text-sm text-gray-500 mt-2 leading-relaxed">
                    I can explain task lifecycle status, analyze result summaries, or provide guidance on
                    scientific workflow requirements based on your project data.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
                  {SUGGESTIONS.map(s => (
                    <button
                      key={s}
                      onClick={() => { setQuery(s); }}
                      className="p-3 text-left bg-gray-50 hover:bg-gray-100 border border-gray-100 rounded-xl text-xs font-medium text-gray-600 transition-colors flex items-center justify-between group"
                    >
                      {s} <ChevronRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`flex gap-3 max-w-[85%] ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                    m.role === 'user' ? 'bg-gray-100 text-gray-600' : 'bg-[#ECFDF5] text-[#065F46]'
                  }`}>
                    {m.role === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                  </div>
                  <div className={`p-4 rounded-2xl text-sm leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-[#065F46] text-white rounded-tr-none'
                      : 'bg-gray-50 text-gray-800 border border-gray-100 rounded-tl-none shadow-sm'
                  }`}>
                    {m.content}
                  </div>
                </div>
              </div>
            ))}
            {ask.isPending && (
              <div className="flex justify-start">
                <div className="flex gap-3 max-w-[85%]">
                   <div className="w-8 h-8 rounded-lg bg-[#ECFDF5] text-[#065F46] flex items-center justify-center shrink-0">
                      <Bot className="w-4 h-4" />
                   </div>
                   <div className="p-4 rounded-2xl bg-gray-50 border border-gray-100 rounded-tl-none shadow-sm flex items-center gap-2">
                      <div className="w-1.5 h-1.5 bg-[#065F46] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                      <div className="w-1.5 h-1.5 bg-[#065F46] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                      <div className="w-1.5 h-1.5 bg-[#065F46] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                   </div>
                </div>
              </div>
            )}
          </div>

          {/* Input Area */}
          <div className="p-6 border-t border-gray-100 bg-white">
            <form className="relative" onSubmit={onSubmit}>
              <input
                aria-label="Agent query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Message Neuro Agent..."
                className="w-full pl-12 pr-24 py-4 bg-gray-50 border border-gray-200 rounded-2xl text-sm outline-none focus:border-[#065F46] focus:bg-white transition-all shadow-inner"
              />
              <div className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">
                <Command className="w-5 h-5" />
              </div>
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <button
                  type="submit"
                  disabled={!query.trim() || ask.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-[#065F46] text-white rounded-xl font-bold text-xs hover:bg-[#044E3A] disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md active:scale-95"
                >
                  <Send className="w-3.5 h-3.5" /> Send
                </button>
              </div>
            </form>
            <div className="mt-3 text-center">
              <span className="text-[10px] text-gray-400 font-medium uppercase tracking-widest">Grounded on internal scientific records & docs</span>
            </div>
          </div>
        </div>

        {/* Evidence Sidebar */}
        <aside className="w-[340px] flex flex-col gap-6">
          {/* RAG Status */}
          <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between mb-4">
               <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                 <Cpu className="w-3.5 h-3.5" /> Intelligence
               </h3>
               <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Model Gateway</span>
                <span className="text-xs font-semibold text-gray-900">{modelGatewayLabel}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Gateway Detail</span>
                <span className="text-xs font-semibold text-gray-900">{modelGatewayDetail}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">SDK Route</span>
                <span className="text-xs font-semibold text-gray-900">{sdkRoute}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Tool Loop</span>
                <span className="text-xs font-semibold text-gray-900">{toolLoop}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Retrieval Model</span>
                <span className="text-xs font-semibold text-gray-900">{retrievalLabel}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Vector Index</span>
                <span className="text-xs font-semibold text-gray-900">{engineLabel}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Indexed Content</span>
                <span className="text-xs font-semibold text-gray-900">{documentCount} docs / {chunkCount} chunks</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">LlamaIndex</span>
                <span className="text-xs font-semibold text-gray-900">{llamaIndexAvailable ? 'available' : 'unavailable'}</span>
              </div>
            </div>
          </div>

          {/* Evidence Review */}
          <div className="flex-1 bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2 font-bold text-gray-800 text-xs uppercase tracking-wider">
              <History className="w-4 h-4 text-[#065F46]" /> Evidence Review
            </div>
            <div className="flex-1 overflow-y-auto p-5 space-y-6">
              {lastResponse ? (
                <>
                  <div>
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Intent Detection</div>
                    <div className="p-2 bg-gray-50 rounded-lg border border-gray-100 text-xs font-medium text-gray-600">
                      {lastResponse.intent || 'Scientific Query'}
                    </div>
                  </div>

                  <div>
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Recommended Next Step</div>
                    <div className="p-3 bg-[#ECFDF5] rounded-lg border border-[#065F46]/10 text-xs font-semibold text-[#065F46] leading-relaxed">
                      {lastResponse.recommended_next_step || lastResponse.tool_chain_hint || 'Verify result summary details.'}
                    </div>
                  </div>

                  {pendingConfirmation ? (
                    <div>
                      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Approval required</div>
                      <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                        <div className="grid grid-cols-2 gap-2">
                          <span className="text-amber-700">Workflow</span>
                          <span className="truncate font-semibold text-right">{String(pendingConfirmation.confirmation.workflow_type || 'unknown')}</span>
                          <span className="text-amber-700">Series</span>
                          <span className="font-semibold text-right">#{String(pendingConfirmation.confirmation.series_id || 'unknown')}</span>
                        </div>
                        <div className="rounded-md border border-amber-200 bg-white px-3 py-2">
                          <div className="font-bold text-amber-900">Task not created yet</div>
                          <div className="mt-1 text-[11px] text-amber-700">Backend API creates the task after approval.</div>
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            disabled={resume.isPending}
                            onClick={() => resume.mutate({
                              approved: true,
                              confirmation: pendingConfirmation.confirmation,
                              threadId: pendingConfirmation.threadId,
                            })}
                            className="flex-1 rounded-md bg-[#065F46] px-3 py-2 text-[11px] font-bold text-white shadow-sm hover:bg-[#044E3A] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Approve workflow
                          </button>
                          <button
                            type="button"
                            disabled={resume.isPending}
                            onClick={() => resume.mutate({
                              approved: false,
                              confirmation: pendingConfirmation.confirmation,
                              threadId: pendingConfirmation.threadId,
                            })}
                            className="rounded-md border border-amber-200 bg-white px-3 py-2 text-[11px] font-bold text-amber-800 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : null}

                  <div>
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Tool Invocations</div>
                    <pre className="p-3 bg-gray-50 rounded-lg border border-gray-100 text-[10px] font-mono text-gray-500 overflow-auto max-h-40">
                      {safeEvidenceJson(lastResponse.tool_invocations || [])}
                    </pre>
                  </div>

                  <div>
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Internal Citations</div>
                    <div className="space-y-2">
                      {(lastResponse.citations || []).length > 0 ? (lastResponse.citations || []).slice(0, 3).map((c, i) => (
                        <div key={i} className="p-2 bg-gray-50 rounded-lg border border-gray-100 text-[10px] text-gray-500 truncate">
                          {c.path || c.title || 'Source doc'}
                        </div>
                      )) : (
                        <div className="text-[10px] text-gray-400 italic">No external citations found.</div>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center opacity-30 px-6">
                  <MessageSquare className="w-12 h-12 mb-3" />
                  <p className="text-xs text-gray-500">Ask a question to see grounding evidence and tools used for the response.</p>
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
