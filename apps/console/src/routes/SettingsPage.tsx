import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Cpu,
  Globe,
  Key,
  Layers,
  Save,
  ShieldCheck,
  Terminal,
  Zap
} from 'lucide-react';
import { useState } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { api, getApiBase, resetApiBase, setApiBase } from '../lib/api';
import { queryKeys } from '../lib/query';

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: deployment, isError: deploymentError } = useQuery({ queryFn: api.deployment, queryKey: queryKeys.deployment });
  const { data: runtime, isError: runtimeError } = useQuery({ queryFn: api.runtimeContainers, queryKey: queryKeys.runtime, retry: false });
  const [apiBaseInput, setApiBaseInput] = useState(getApiBase());
  const productionReadiness = deployment?.production_readiness;
  const readinessBlocked = productionReadiness?.ready === false;
  const fastLaunchReadiness = deployment?.fast_launch_readiness;
  const launchBlocked = fastLaunchReadiness?.ready === false;
  const modelTarget = fastLaunchReadiness?.checks?.model_gateway_target;
  const modelTargetLabel = [
    modelTarget?.actual_provider_profile,
    modelTarget?.actual_model,
    modelTarget?.actual_wire_api,
  ].filter(Boolean).join(' / ') || 'Not reported';
  const agentBoundaryPassed = fastLaunchReadiness?.checks?.agent_task_boundary?.status === 'passed';
  const remoteAcceptance = fastLaunchReadiness?.checks?.strict_remote_acceptance;
  const apiDisconnected = deploymentError || runtimeError;

  function handleSave() {
    setApiBase(apiBaseInput);
    setApiBaseInput(getApiBase());
    refreshConnectionStatus();
  }

  function handleReset() {
    resetApiBase();
    setApiBaseInput(getApiBase());
    refreshConnectionStatus();
  }

  function refreshConnectionStatus() {
    queryClient.invalidateQueries({ queryKey: queryKeys.deployment });
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime });
  }

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <PageHeader
        description="Runtime, API, and agent configuration signals used by the scientific console."
        eyebrow="Environment"
        title="Settings"
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* API Configuration */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden transition-all hover:shadow-md">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between font-bold text-gray-800 text-xs uppercase tracking-wider">
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-[#065F46]" /> API Connection
            </div>
            <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold ${
              apiDisconnected ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
            }`}>
              <div className={`w-1.5 h-1.5 rounded-full ${apiDisconnected ? 'bg-red-500' : 'bg-green-500 animate-pulse'}`}></div>
              {apiDisconnected ? 'API disconnected' : 'Connected'}
            </span>
          </div>
          <div className="p-6 space-y-5">
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5" htmlFor="api-base-endpoint">
                <Terminal className="w-3.5 h-3.5" /> API Base Endpoint
              </label>
              <input
                className="w-full p-3 bg-gray-50 border border-gray-100 rounded-xl font-mono text-xs text-gray-700 outline-none focus:border-[#065F46] focus:ring-1 focus:ring-[#065F46]"
                id="api-base-endpoint"
                onChange={(event) => setApiBaseInput(event.target.value)}
                value={apiBaseInput}
              />
              <p className="text-[10px] text-gray-400 italic">Target backend for all scientific queries and ingest triggers.</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5" /> Public API Base
              </label>
              <div className="p-3 bg-white border border-gray-200 rounded-xl flex items-center justify-between gap-3">
                <span className={`min-w-0 truncate font-mono text-xs ${
                  deploymentError || !deployment?.api_base_hint ? 'text-amber-700' : 'text-gray-700'
                }`}>
                  {deployment?.api_base_hint || 'Not reported'}
                </span>
              </div>
              <p className="text-[10px] text-gray-400 italic">Backend-declared public HTTPS endpoint for production callbacks and browser clients.</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5" /> Backend Runtime Mode
              </label>
              <div className="p-3 bg-white border border-gray-200 rounded-xl flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-800 capitalize">
                  {deploymentError ? 'Backend status unavailable' : deployment?.backend_runtime_mode || 'local'}
                </span>
                <span className="px-2 py-0.5 rounded bg-[#ECFDF5] text-[#065F46] text-[10px] font-bold uppercase tracking-tight">
                  {deploymentError ? 'Unavailable' : deployment?.backend_runtime_mode === 'remote' ? 'Production' : 'Development'}
                </span>
              </div>
            </div>

            {productionReadiness?.required ? (
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5" /> Production Readiness
                </label>
                <div className={`p-3 border rounded-xl space-y-2 ${
                  readinessBlocked ? 'bg-amber-50 border-amber-100' : 'bg-green-50 border-green-100'
                }`}>
                  <div className="flex items-center justify-between gap-3">
                    <span className={`text-sm font-bold ${readinessBlocked ? 'text-amber-800' : 'text-green-700'}`}>
                      {readinessBlocked ? 'Blocked' : 'Ready'}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-tight ${
                      readinessBlocked ? 'bg-white text-amber-700 border border-amber-200' : 'bg-white text-green-700 border border-green-200'
                    }`}>
                      Production
                    </span>
                  </div>
                  {readinessBlocked ? (
                    <div className="space-y-1">
                      {(productionReadiness.blocking_reasons || []).map((reason) => (
                        <div key={reason} className="text-xs font-medium text-amber-700">{reason}</div>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}

            {fastLaunchReadiness ? (
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5" /> Fast Launch Readiness
                </label>
                <div className={`p-3 border rounded-xl space-y-3 ${
                  launchBlocked ? 'bg-amber-50 border-amber-100' : 'bg-green-50 border-green-100'
                }`}>
                  <div className="flex items-center justify-between gap-3">
                    <span className={`text-sm font-bold ${launchBlocked ? 'text-amber-800' : 'text-green-700'}`}>
                      {launchBlocked ? 'Launch blocked' : 'Launch ready'}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-tight ${
                      launchBlocked ? 'bg-white text-amber-700 border border-amber-200' : 'bg-white text-green-700 border border-green-200'
                    }`}>
                      Main chain
                    </span>
                  </div>
                  <div className="grid gap-2 text-xs sm:grid-cols-2">
                    <div className="rounded-lg border border-white/80 bg-white/70 p-2">
                      <div className="font-bold text-gray-800">Model target</div>
                      <div className="mt-1 font-mono text-[11px] text-gray-600">{modelTargetLabel}</div>
                    </div>
                    <div className="rounded-lg border border-white/80 bg-white/70 p-2">
                      <div className="font-bold text-gray-800">Agent boundary</div>
                      <div className={`mt-1 text-[11px] font-semibold ${agentBoundaryPassed ? 'text-green-700' : 'text-amber-700'}`}>
                        {agentBoundaryPassed ? 'Agent boundary protected' : 'Agent boundary needs review'}
                      </div>
                    </div>
                    <div className="rounded-lg border border-white/80 bg-white/70 p-2">
                      <div className="font-bold text-gray-800">Remote acceptance</div>
                      <div className={`mt-1 text-[11px] font-semibold ${
                        remoteAcceptance?.status === 'passed' ? 'text-green-700' : 'text-amber-700'
                      }`}>
                        {remoteAcceptance?.status === 'passed'
                          ? `Strict remote acceptance ${remoteAcceptance.evidence_id || 'passed'}`
                          : 'Strict remote acceptance missing'}
                      </div>
                    </div>
                    <div className="rounded-lg border border-white/80 bg-white/70 p-2">
                      <div className="font-bold text-gray-800">Result contract</div>
                      <div className="mt-1 text-[11px] font-semibold text-gray-600">
                        Upload, workflow, outputs, summary, manifest
                      </div>
                    </div>
                  </div>
                  {launchBlocked ? (
                    <div className="space-y-1">
                      {(fastLaunchReadiness.blocking_reasons || []).map((reason) => (
                        <div key={reason} className="text-xs font-medium text-amber-700">{reason}</div>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {/* Runtime & Infrastructure */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden transition-all hover:shadow-md">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between font-bold text-gray-800 text-xs uppercase tracking-wider">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#065F46]" /> Infrastructure Signals
            </div>
          </div>
          <div className="p-6 space-y-5">
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl border border-gray-100">
               <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg ${runtime?.fs_license_exists ? 'bg-green-100 text-green-600' : 'bg-amber-100 text-amber-600'}`}>
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-xs font-bold text-gray-900">FreeSurfer License</div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-tight">Required for T1/DWI</div>
                  </div>
               </div>
               <span className={`text-xs font-bold uppercase tracking-wider ${runtime?.fs_license_exists ? 'text-green-600' : 'text-amber-600'}`}>
                 {runtimeError ? 'Container status unavailable' : runtime?.fs_license_exists ? 'Available' : 'Missing'}
               </span>
            </div>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl border border-gray-100">
               <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-blue-100 text-blue-600">
                    <Cpu className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-xs font-bold text-gray-900">Agent Provider</div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-tight">RAG Analysis Engine</div>
                  </div>
               </div>
               <span className="text-xs font-bold text-blue-600 uppercase tracking-wider">
                 {deployment?.agent?.configured === false ? 'not configured' : deployment?.agent?.provider || 'fallback'}
               </span>
            </div>
          </div>
        </div>
      </div>

      {/* Advanced Settings Placeholder */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2 font-bold text-gray-800 text-xs uppercase tracking-wider">
          <Key className="w-4 h-4 text-[#065F46]" /> Security & Access
        </div>
        <div className="p-12 flex flex-col items-center justify-center text-center">
           <div className="w-16 h-16 rounded-2xl bg-gray-50 flex items-center justify-center text-gray-300 mb-4">
             <Key className="w-8 h-8" />
           </div>
           <h3 className="text-gray-900 font-bold">Authentication is Managed Externally</h3>
           <p className="text-xs text-gray-500 max-w-sm mx-auto mt-2 leading-relaxed">
             This console uses token-based session affinity. If you need to rotate
             credentials or change permissions, please contact your systems administrator.
           </p>
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-4">
        <button
          className="px-6 py-2 bg-white border border-gray-200 text-gray-700 rounded-xl text-xs font-bold hover:bg-gray-50 transition-colors"
          onClick={handleReset}
        >
          Reset Defaults
        </button>
        <button
          className="px-8 py-2 bg-[#065F46] text-white rounded-xl text-xs font-bold hover:bg-[#044E3A] transition-colors shadow-lg flex items-center gap-2"
          onClick={handleSave}
        >
          <Save className="w-3.5 h-3.5" /> Save Changes
        </button>
      </div>
    </div>
  );
}
