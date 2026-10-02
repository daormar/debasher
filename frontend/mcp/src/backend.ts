import * as execution from "../../src/api/executionApi";
import * as processes from "../../src/api/processApi";
import * as programFiles from "../../src/api/programFilesApi";
import * as storage from "../../src/storage/programStorage";

// The backend as the MCP server reaches it: the functions of the frontend's
// own clients of the backend (src/api/ and src/storage/), gathered in one
// object, so that the MCP server sends the requests that the editor sends,
// and that a test hands the MCP tools a fake one instead.

export const httpBackend = {
  loadProgram: storage.loadProgram,
  saveProgram: storage.saveProgram,
  importProgram: storage.importProgram,
  validateProcessName: processes.validateProcessName,
  suggestProcessNames: processes.suggestProcessNames,
  getProcessInfo: processes.getProcessInfo,
  suggestNodes: processes.suggestNodes,
  getNodeInfo: processes.getNodeInfo,
  validateProgram: execution.validateProgram,
  runTests: execution.runTests,
  checkProgramOptions: execution.checkProgramOptions,
  fetchProgramStatus: execution.fetchProgramStatus,
  getProcessStatuses: execution.getProcessStatuses,
  runProgram: execution.runProgram,
  stopProgram: execution.stopProgram,
  killProgram: execution.killProgram,
  getProcessStdout: execution.getProcessStdout,
  getProcessSchedOut: execution.getProcessSchedOut,
  getProcessOpts: execution.getProcessOpts,
  getProcessResolvedOptions: execution.getProcessResolvedOptions,
  getProcessTasks: execution.getProcessTasks,
  resetOutputDir: execution.resetOutputDir,
  resetProgramState: execution.resetProgramState,
  inspectNode: execution.inspectNode,
  takeSnapshot: execution.takeSnapshot,
  restartNode: execution.restartNode,
  relaunchNode: execution.relaunchNode,
  launchedWithNoHoldFifos: execution.launchedWithNoHoldFifos,
  writeResidentFifo: execution.writeResidentFifo,
  readResidentFifo: execution.readResidentFifo,
  getFileTree: programFiles.getFileTree,
  getFileContent: programFiles.getFileContent,
  writeFileContent: programFiles.writeFileContent,
  deleteEntry: programFiles.deleteEntry,
  moveEntry: programFiles.moveEntry,
};

export type Backend = typeof httpBackend;

/**
 * Sends the requests of the frontend's clients, which name the backend by a
 * path relative to the page that serves them ("/api/..."), to the backend
 * at `url`, by resolving every relative URL that fetch is given against it.
 * Under Node.js there is no page to resolve them against.
 */
export function sendRequestsTo(url: string): void {
  const base = new URL(url);
  const nodeFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    try {
      return await nodeFetch(typeof input === "string" ? new URL(input, base) : input, init);
    } catch (err) {
      // fetch fails only when no answer came at all.
      throw new Error(`Cannot reach the backend at ${base.origin}: is debasher_webui running there? (${err})`);
    }
  };
}
