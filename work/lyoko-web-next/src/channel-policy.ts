// Planning information, not RF authorization or a declaration of compliance.
// Baseline: docs/LYOKO_CHANNEL_POLICY_ES.md; occupied bandwidth matters for DFS.
export type ChannelWidth = 20 | 40 | 80;
const low = [36, 40, 44, 48, 52, 56, 60, 64];
const middle = [100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144];
const high = [149, 153, 157, 161, 165, 169, 173, 177];
export const CHANNEL_CATALOGUE = [...low, ...middle, ...high];

export function channelLabelForWidth(channel: number, width: ChannelWidth): string {
  const info = describeChannel(channel, width);
  if (info.cacSeconds === null) return `${channel} · fuera del perfil verificado`;
  if (info.cacSeconds === 0) return `${channel} · sin DFS`;
  return `${channel} · DFS · CAC ${info.cacSeconds === 600 ? "10 min" : `${info.cacSeconds} s`} (${width} MHz)`;
}

export function describeChannel(channel: number, width: ChannelWidth) {
  const group = [low, middle, high].find(values => values.includes(channel));
  const base = { channel, width, nopSeconds: 0, cacSeconds: null as number | null, lowMHz: null as number | null, highMHz: null as number | null };
  if (!group || ![20, 40, 80].includes(width)) return { ...base, category: "unknown" as const,
    reason: "Canal o combinación no descritos por este catálogo. Frecuencia, soporte de placa y condiciones de uso pendientes de verificar." };
  const count = width / 20;
  const block = group.slice(Math.floor(group.indexOf(channel) / count) * count, Math.floor(group.indexOf(channel) / count) * count + count);
  if (block.length !== count) return { ...base, category: "unknown" as const, reason: "Bloque de canales incompleto." };
  const lowMHz = 5000 + block[0] * 5 - 10;
  const highMHz = 5000 + block[block.length - 1] * 5 + 10;
  const supportedBand = [[5150, 5250], [5250, 5350], [5470, 5725]].some(([start, end]) => lowMHz >= start && highMHz <= end);
  if (!supportedBand) return { ...base, lowMHz, highMHz, category: "outside-profile" as const,
    reason: "El bloque nominal queda fuera del perfil RLAN UE aquí documentado. Otros usos nacionales o límites de potencia no están verificados; no equivale a autorización de emisión." };
  const dfs = lowMHz >= 5250;
  const weather = dfs && lowMHz < 5650 && highMHz > 5600;
  return { ...base, lowMHz, highMHz, category: weather ? "weather-dfs" as const : dfs ? "dfs" as const : "non-dfs" as const,
    cacSeconds: weather ? 600 : dfs ? 60 : 0, nopSeconds: dfs ? 1800 : 0,
    reason: weather ? "El ancho nominal solapa 5600–5650 MHz: se requiere el CAC meteorológico del perfil."
      : dfs ? "Requiere CAC y detección continua; un radar obliga a evacuar y respetar NOP."
      : "Sin CAC DFS en este perfil. Siguen aplicando potencia, entorno de uso y condiciones del dominio." };
}
