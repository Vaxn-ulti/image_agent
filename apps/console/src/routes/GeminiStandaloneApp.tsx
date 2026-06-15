import {
  BarChart2,
  BookOpen,
  Brain,
  CheckCircle,
  ChevronDown,
  ChevronLeft,
  CloudUpload,
  Eye,
  FileText,
  Home,
  Play,
  RotateCcw,
  Settings,
  SlidersHorizontal,
  Trash2,
  Download,
  Activity,
  CheckCircle2
} from 'lucide-react';

export function GeminiStandaloneApp() {
  return (
    <div className="flex h-screen bg-[#F8FAFC] text-[#1E293B] font-sans antialiased overflow-hidden">
      {/* Sidebar */}
      <aside className="w-[260px] flex-shrink-0 border-r border-[#E2E8F0] bg-white flex flex-col justify-between overflow-y-auto">
        <div>
          {/* Logo */}
          <div className="flex items-center gap-3 px-6 py-6 border-b border-[#E2E8F0]">
            <div className="text-green-700">
              <Brain className="w-8 h-8" />
            </div>
            <div>
              <div className="font-bold text-sm leading-tight text-gray-900">Neuro Imaging Agent</div>
              <div className="text-xs text-gray-500">MRI Processing Console</div>
            </div>
            <div className="ml-auto text-gray-400">
              <ChevronLeft className="w-4 h-4" />
            </div>
          </div>

          {/* Navigation */}
          <div className="px-4 py-4">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2 px-2">Navigation</div>
            <nav className="space-y-1">
              <a href="#" className="flex items-center gap-3 px-3 py-2 bg-[#ECFDF5] text-[#065F46] rounded-md font-medium text-sm">
                <Home className="w-4 h-4" /> Overview
              </a>
              <a href="#" className="flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-md font-medium text-sm">
                <CloudUpload className="w-4 h-4" /> Upload Data
              </a>
              <a href="#" className="flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-md font-medium text-sm">
                <SlidersHorizontal className="w-4 h-4" /> Preprocessing
              </a>
              <a href="#" className="flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-md font-medium text-sm">
                <Brain className="w-4 h-4" /> Segmentation
              </a>
              <a href="#" className="flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-md font-medium text-sm">
                <CheckCircle className="w-4 h-4" /> QC Review
              </a>
              <a href="#" className="flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-md font-medium text-sm">
                <FileText className="w-4 h-4" /> Report
              </a>
              <a href="#" className="flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-md font-medium text-sm">
                <BarChart2 className="w-4 h-4" /> Results
              </a>
            </nav>
          </div>

          {/* Actions */}
          <div className="px-4 py-2">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2 px-2">Actions</div>
            <div className="space-y-2">
              <button className="w-full flex items-center justify-center gap-2 bg-[#065F46] text-white px-4 py-2.5 rounded-md font-medium text-sm hover:bg-[#044E3A] transition-colors shadow-sm">
                <Play className="w-4 h-4" /> Run Pipeline
              </button>
              <button className="w-full flex items-center justify-center gap-2 border border-gray-300 bg-white text-gray-700 px-4 py-2.5 rounded-md font-medium text-sm hover:bg-gray-50 transition-colors">
                <BookOpen className="w-4 h-4" /> Docs
              </button>
            </div>
          </div>

          {/* Session */}
          <div className="px-4 py-4">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2 px-2">Session</div>
            <div className="bg-gray-50 rounded-lg p-3 space-y-4 text-xs border border-[#E2E8F0]">
              <div>
                <div className="text-gray-500 mb-1">Active Session</div>
                <div className="flex items-center gap-1.5 font-medium text-gray-700">
                  <div className="w-2 h-2 rounded-full bg-green-500"></div> Ready
                </div>
              </div>
              <div>
                <div className="text-gray-500 mb-1">Workspace</div>
                <div className="flex items-center justify-between font-medium text-gray-700 cursor-pointer">
                  Default Workspace <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                </div>
              </div>
              <div>
                <div className="text-gray-500 mb-1">Python Environment</div>
                <div className="flex items-center justify-between font-medium text-gray-700 cursor-pointer">
                  neuro-agent (3.10) <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer Collapse */}
        <div className="p-4 border-t border-[#E2E8F0]">
          <button className="flex items-center gap-2 text-gray-500 hover:text-gray-700 text-sm font-medium">
            <ChevronLeft className="w-4 h-4" /> Collapse sidebar
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        {/* Top Header */}
        <header className="flex justify-end p-6 gap-3">
          <button className="flex items-center gap-2 border border-gray-200 bg-white text-gray-700 px-3 py-1.5 rounded-md text-sm font-medium hover:bg-gray-50 shadow-sm">
            <Settings className="w-4 h-4" /> Settings
          </button>
          <div className="flex items-center gap-2 border border-gray-200 bg-white px-1.5 py-1.5 rounded-md cursor-pointer hover:bg-gray-50 shadow-sm">
            <div className="w-6 h-6 rounded bg-[#065F46] text-white flex items-center justify-center text-xs font-bold">NR</div>
            <ChevronDown className="w-3.5 h-3.5 text-gray-500 mr-1" />
          </div>
        </header>

        {/* Page Content */}
        <div className="max-w-6xl mx-auto px-6 pb-12">
          {/* Title Area */}
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-3 tracking-tight">Brain Imaging Processing Agent</h1>
            <p className="text-gray-500 max-w-3xl text-sm leading-relaxed">
              Upload brain MRI data in DICOM or NIfTI format and run automated preprocessing, segmentation,
              quality control, and report generation â€?all in one streamlined workflow.
            </p>
          </div>

          <div className="grid grid-cols-12 gap-6">
            {/* Upload Data Card */}
            <div className="col-span-5 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
              <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2 font-semibold text-gray-800 text-sm">
                <CloudUpload className="w-4 h-4 text-green-700" /> Upload Data
              </div>
              <div className="p-5 flex-1 flex flex-col">
                <div className="border-2 border-dashed border-gray-200 rounded-lg flex-1 flex flex-col items-center justify-center p-6 bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer group">
                  <CloudUpload className="w-10 h-10 text-gray-400 mb-3 group-hover:text-green-600 transition-colors" />
                  <div className="text-sm font-medium text-gray-700 mb-1">Drag & drop DICOM or NIfTI files here</div>
                  <div className="text-xs text-gray-500 mb-4">or click to browse</div>
                  <button className="border border-gray-300 bg-white text-gray-700 px-4 py-1.5 rounded-md text-sm font-medium shadow-sm group-hover:border-green-600 group-hover:text-green-700 transition-colors">
                    Browse Files
                  </button>
                </div>
                <div className="mt-4 flex justify-between items-center text-xs">
                  <span className="text-gray-500">Supported: DICOM (.dcm), NIfTI (.nii, .nii.gz)</span>
                  <a href="#" className="text-green-700 hover:underline font-medium">Learn more</a>
                </div>
              </div>
            </div>

            {/* Workflow Status Card */}
            <div className="col-span-7 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2 font-semibold text-gray-800 text-sm">
                <Activity className="w-4 h-4 text-green-700" /> Workflow Status
              </div>
              <div className="p-6">
                <div className="relative space-y-6 before:absolute before:inset-0 before:ml-[11px] before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-300 before:to-transparent">

                  {/* Step 1 */}
                  <div className="relative flex items-center gap-4 text-sm">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-green-500 flex items-center justify-center text-white z-10 border-2 border-white shadow-sm">
                      <CheckCircle2 className="w-4 h-4" />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900">Intake</h4>
                      <p className="text-xs text-gray-500">Data uploaded</p>
                    </div>
                    <div className="text-right text-xs text-gray-500 flex flex-col items-end">
                      <span className="font-medium text-gray-900">Completed</span>
                      <span>2 min ago</span>
                    </div>
                  </div>

                  {/* Step 2 */}
                  <div className="relative flex items-center gap-4 text-sm">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-green-500 flex items-center justify-center text-white z-10 border-2 border-white shadow-sm">
                      <CheckCircle2 className="w-4 h-4" />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900">Preprocessing</h4>
                      <p className="text-xs text-gray-500">Bias correction, skull stripping, normalization</p>
                    </div>
                    <div className="text-right text-xs text-gray-500 flex flex-col items-end">
                      <span className="font-medium text-gray-900">Completed</span>
                      <span>1 min ago</span>
                    </div>
                  </div>

                  {/* Step 3 */}
                  <div className="relative flex items-center gap-4 text-sm">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-white border-2 border-blue-500 flex items-center justify-center z-10 shadow-sm relative">
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                    </div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900">Segmentation</h4>
                      <p className="text-xs text-gray-500">Automated tissue & structure segmentation</p>
                    </div>
                    <div className="text-right text-xs text-blue-600 flex flex-col items-end">
                      <span className="font-medium">In Progress</span>
                      <span>12%</span>
                    </div>
                  </div>

                  {/* Step 4 */}
                  <div className="relative flex items-center gap-4 text-sm opacity-50">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-200 border-2 border-white flex items-center justify-center z-10 text-[10px] font-bold text-gray-500 shadow-sm">
                      4
                    </div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900">QC Review</h4>
                      <p className="text-xs text-gray-500">Quality control checks</p>
                    </div>
                    <div className="text-right text-xs text-gray-500">
                      Pending
                    </div>
                  </div>

                  {/* Step 5 */}
                  <div className="relative flex items-center gap-4 text-sm opacity-50">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-200 border-2 border-white flex items-center justify-center z-10 text-[10px] font-bold text-gray-500 shadow-sm">
                      5
                    </div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900">Report Generation</h4>
                      <p className="text-xs text-gray-500">Generate PDF report</p>
                    </div>
                    <div className="text-right text-xs text-gray-500">
                      Pending
                    </div>
                  </div>

                </div>
              </div>
            </div>

            {/* Pipeline Parameters Card */}
            <div className="col-span-5 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
              <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between font-semibold text-gray-800 text-sm">
                <div className="flex items-center gap-2">
                  <SlidersHorizontal className="w-4 h-4 text-green-700" /> Pipeline Parameters
                </div>
                <ChevronDown className="w-4 h-4 text-gray-400" />
              </div>
              <div className="p-5 flex-1 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                    Preprocessing Preset <span className="text-gray-400 text-[10px] w-3 h-3 rounded-full border border-gray-300 inline-flex items-center justify-center">i</span>
                  </span>
                  <select className="text-sm border border-gray-200 rounded-md px-3 py-1.5 bg-gray-50 outline-none w-[200px]">
                    <option>Standard (Recommended)</option>
                  </select>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                    Skull Stripping <span className="text-gray-400 text-[10px] w-3 h-3 rounded-full border border-gray-300 inline-flex items-center justify-center">i</span>
                  </span>
                  <div className="w-[200px]">
                    <div className="w-10 h-5 bg-green-600 rounded-full relative cursor-pointer">
                      <div className="w-4 h-4 bg-white rounded-full absolute top-0.5 right-0.5 shadow-sm"></div>
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                    Bias Field Correction <span className="text-gray-400 text-[10px] w-3 h-3 rounded-full border border-gray-300 inline-flex items-center justify-center">i</span>
                  </span>
                  <div className="w-[200px]">
                    <div className="w-10 h-5 bg-green-600 rounded-full relative cursor-pointer">
                      <div className="w-4 h-4 bg-white rounded-full absolute top-0.5 right-0.5 shadow-sm"></div>
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                    Tissue Segmentation <span className="text-gray-400 text-[10px] w-3 h-3 rounded-full border border-gray-300 inline-flex items-center justify-center">i</span>
                  </span>
                  <select className="text-sm border border-gray-200 rounded-md px-3 py-1.5 bg-gray-50 outline-none w-[200px]">
                    <option>FastSurfer (Recommended)</option>
                  </select>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                    Parcellation Atlas <span className="text-gray-400 text-[10px] w-3 h-3 rounded-full border border-gray-300 inline-flex items-center justify-center">i</span>
                  </span>
                  <select className="text-sm border border-gray-200 rounded-md px-3 py-1.5 bg-gray-50 outline-none w-[200px]">
                    <option>Desikan-Killiany (68)</option>
                  </select>
                </div>
                <div className="pt-2">
                  <button className="text-sm font-medium text-gray-600 flex items-center gap-1 hover:text-gray-800">
                    Advanced Options <ChevronDown className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>

            {/* Recent Runs Card */}
            <div className="col-span-7 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
              <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between font-semibold text-gray-800 text-sm">
                <div className="flex items-center gap-2">
                  <RotateCcw className="w-4 h-4 text-green-700" /> Recent Runs
                </div>
                <a href="#" className="text-green-700 hover:underline font-medium text-xs">View all</a>
              </div>
              <div className="overflow-x-auto flex-1">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-gray-50 text-gray-500 border-b border-gray-100">
                    <tr>
                      <th className="px-5 py-3 font-medium">ID</th>
                      <th className="px-5 py-3 font-medium">Dataset</th>
                      <th className="px-5 py-3 font-medium">Status</th>
                      <th className="px-5 py-3 font-medium">Completed</th>
                      <th className="px-5 py-3 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-gray-700">
                    <tr className="hover:bg-gray-50 transition-colors">
                      <td className="px-5 py-3 font-mono text-xs text-gray-500">RUN-2024-05-21-001</td>
                      <td className="px-5 py-3">sub-001_T1w.nii.gz</td>
                      <td className="px-5 py-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">
                          Completed
                        </span>
                      </td>
                      <td className="px-5 py-3 text-gray-500">May 21, 2024 10:42 AM</td>
                      <td className="px-5 py-3 flex items-center justify-end gap-2">
                        <button className="p-1 hover:bg-gray-200 rounded text-gray-500"><Eye className="w-4 h-4" /></button>
                        <button className="p-1 hover:bg-gray-200 rounded text-gray-500"><Download className="w-4 h-4" /></button>
                      </td>
                    </tr>
                    <tr className="hover:bg-gray-50 transition-colors">
                      <td className="px-5 py-3 font-mono text-xs text-gray-500">RUN-2024-05-21-002</td>
                      <td className="px-5 py-3">sub-002_T1w.nii.gz</td>
                      <td className="px-5 py-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">
                          Completed
                        </span>
                      </td>
                      <td className="px-5 py-3 text-gray-500">May 21, 2024 09:18 AM</td>
                      <td className="px-5 py-3 flex items-center justify-end gap-2">
                        <button className="p-1 hover:bg-gray-200 rounded text-gray-500"><Eye className="w-4 h-4" /></button>
                        <button className="p-1 hover:bg-gray-200 rounded text-gray-500"><Download className="w-4 h-4" /></button>
                      </td>
                    </tr>
                    <tr className="hover:bg-gray-50 transition-colors">
                      <td className="px-5 py-3 font-mono text-xs text-gray-500">RUN-2024-05-21-003</td>
                      <td className="px-5 py-3">sub-003_T1w.nii.gz</td>
                      <td className="px-5 py-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 border border-blue-200">
                          In Progress
                        </span>
                      </td>
                      <td className="px-5 py-3 text-gray-500">--</td>
                      <td className="px-5 py-3 flex items-center justify-end gap-2">
                        <button className="p-1 hover:bg-red-50 rounded text-gray-400 hover:text-red-500"><Trash2 className="w-4 h-4" /></button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Results Preview Card */}
            <div className="col-span-12 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col mt-2">
              <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2 font-semibold text-gray-800 text-sm">
                <BarChart2 className="w-4 h-4 text-green-700" /> Results Preview
              </div>
              <div className="p-6 flex gap-8">
                {/* Left Info Column */}
                <div className="w-[180px] flex-shrink-0 space-y-4 text-sm">
                  <div>
                    <div className="text-gray-500 text-xs mb-1">Dataset</div>
                    <div className="font-medium text-gray-800 truncate">sub-001_T1w.nii.gz</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-xs mb-1">Date</div>
                    <div className="font-medium text-gray-800">May 21, 2024 10:42 AM</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-xs mb-1">Pipeline</div>
                    <div className="font-medium text-gray-800">Standard</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-xs mb-1">Duration</div>
                    <div className="font-medium text-gray-800">18m 47s</div>
                  </div>
                  <div className="pt-2">
                    <button className="w-full flex justify-center items-center gap-2 border border-gray-300 bg-white text-gray-700 px-3 py-2 rounded-md font-medium text-xs hover:bg-gray-50 shadow-sm">
                      View Full Results â†?
                    </button>
                  </div>
                </div>

                {/* Right Images Gallery */}
                <div className="flex-1">
                  <div className="grid grid-cols-4 gap-4 mb-6">
                    {/* Img 1 */}
                    <div className="flex flex-col items-center">
                      <span className="text-xs font-medium text-gray-700 mb-2">T1w (Axial)</span>
                      <div className="w-full aspect-square bg-black rounded-xl overflow-hidden relative shadow-inner">
                        <div className="absolute inset-0 bg-gradient-to-tr from-gray-900 to-gray-700 opacity-80 mix-blend-overlay"></div>
                        <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-[10px]">Image Block</div>
                        <span className="absolute bottom-2 left-3 text-white text-xs font-bold font-mono">R</span>
                        <span className="absolute bottom-2 right-3 text-white text-xs font-bold font-mono">L</span>
                      </div>
                    </div>
                    {/* Img 2 */}
                    <div className="flex flex-col items-center">
                      <span className="text-xs font-medium text-gray-700 mb-2">T1w (Sagittal)</span>
                      <div className="w-full aspect-square bg-black rounded-xl overflow-hidden relative shadow-inner">
                         <div className="absolute inset-0 bg-gradient-to-tr from-gray-800 to-gray-600 opacity-80 mix-blend-overlay"></div>
                         <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-[10px]">Image Block</div>
                         <span className="absolute bottom-2 left-3 text-white text-xs font-bold font-mono">A</span>
                         <span className="absolute bottom-2 right-3 text-white text-xs font-bold font-mono">P</span>
                      </div>
                    </div>
                    {/* Img 3 */}
                    <div className="flex flex-col items-center">
                      <span className="text-xs font-medium text-gray-700 mb-2">T1w (Coronal)</span>
                      <div className="w-full aspect-square bg-black rounded-xl overflow-hidden relative shadow-inner">
                         <div className="absolute inset-0 bg-gradient-to-b from-gray-900 via-gray-700 to-gray-900 opacity-80 mix-blend-overlay"></div>
                         <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-[10px]">Image Block</div>
                         <span className="absolute bottom-2 left-3 text-white text-xs font-bold font-mono">R</span>
                         <span className="absolute bottom-2 right-3 text-white text-xs font-bold font-mono">L</span>
                      </div>
                    </div>
                    {/* Img 4 */}
                    <div className="flex flex-col items-center">
                      <span className="text-xs font-medium text-gray-700 mb-2">Segmentation (Axial)</span>
                      <div className="w-full aspect-square bg-black rounded-xl overflow-hidden relative shadow-inner">
                         <div className="absolute inset-0 bg-gradient-to-tr from-blue-900/40 via-purple-900/40 to-pink-900/40 opacity-80 mix-blend-overlay"></div>
                         <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-[10px]">Color Block</div>
                         <span className="absolute bottom-2 left-3 text-white text-xs font-bold font-mono">R</span>
                         <span className="absolute bottom-2 right-3 text-white text-xs font-bold font-mono">L</span>
                      </div>
                    </div>
                  </div>

                  {/* Legend */}
                  <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-gray-600 px-4">
                    <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-gray-800"></div> Background</div>
                    <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-green-500"></div> Gray Matter</div>
                    <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-blue-300"></div> White Matter</div>
                    <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-blue-600"></div> CSF</div>
                    <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-purple-600"></div> Deep Gray Matter</div>
                    <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-pink-400"></div> Brainstem</div>
                    <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-pink-600"></div> Cerebellum</div>
                    <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-gray-300"></div> Other</div>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </main>
    </div>
  );
}
