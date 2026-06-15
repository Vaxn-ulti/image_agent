import { useQuery } from '@tanstack/react-query';
import {
  Cpu,
  Globe,
  Key,
  Layers,
  Save,
  ShieldCheck,
  Terminal,
  Zap
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { api, getApiBase } from '../lib/api';
import { queryKeys } from '../lib/query';

export function SettingsPage() {
  const { data: deployment } = useQuery({ queryFn: api.deployment, queryKey: queryKeys.deployment });
  const { data: runtime } = useQuery({ queryFn: api.runtimeContainers, queryKey: queryKeys.runtime, retry: false });

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
            <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-green-50 text-green-700 text-[10px] font-bold">
              <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></div> Connected
            </span>
          </div>
          <div className="p-6 space-y-5">
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5" /> API Base Endpoint
              </label>
              <div className="p-3 bg-gray-50 border border-gray-100 rounded-xl font-mono text-xs text-gray-600 break-all">
                {getApiBase()}
              </div>
              <p className="text-[10px] text-gray-400 italic">Target backend for all scientific queries and ingest triggers.</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5" /> Backend Runtime Mode
              </label>
              <div className="p-3 bg-white border border-gray-200 rounded-xl flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-800 capitalize">
                  {deployment?.backend_runtime_mode || 'local'}
                </span>
                <span className="px-2 py-0.5 rounded bg-[#ECFDF5] text-[#065F46] text-[10px] font-bold uppercase tracking-tight">
                  {deployment?.backend_runtime_mode === 'remote' ? 'Production' : 'Development'}
                </span>
              </div>
            </div>
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
                 {runtime?.fs_license_exists ? 'Available' : 'Missing'}
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
                 {deployment?.agent?.provider || 'fallback'}
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
        <button className="px-6 py-2 bg-white border border-gray-200 text-gray-700 rounded-xl text-xs font-bold hover:bg-gray-50 transition-colors">
          Reset Defaults
        </button>
        <button className="px-8 py-2 bg-[#065F46] text-white rounded-xl text-xs font-bold hover:bg-[#044E3A] transition-colors shadow-lg flex items-center gap-2">
          <Save className="w-3.5 h-3.5" /> Save Changes
        </button>
      </div>
    </div>
  );
}
