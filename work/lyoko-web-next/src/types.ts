export type RadioState = {
  id: "2g" | "5g";
  state: string;
  ssid: string;
  channel: number;
  bandwidth: number | string;
  clients: number;
  security: string;
  txPower?: string;
};

export type Snapshot = {
  source: "router" | "mock";
  version: string;
  kernel: string;
  uptimeSeconds: number;
  health: string;
  temperature?: number;
  memoryFreeMiB: number;
  radios: RadioState[];
  optimization: {
    mode: string;
    decision: string;
    stableFor: number;
    threshold: number;
    persistence: string;
    supervisorRunning: boolean;
    engineRunning: boolean;
    lastSequence: number;
    automaticApply: boolean;
  };
  capabilities: string[];
};
