/**
 * Parse one server-sent-event block (the text between blank lines) into
 * `{ event, data }`, or `null` for a comment such as the server's keep-alive.
 * `data` is JSON: every event this backend sends carries a JSON payload.
 *
 * @param {string} block
 * @returns {{ event: string, data: any } | null}
 */
export const parseSseBlock = (block) => {
  let event = 'message';
  const dataLines = [];
  block.split('\n').forEach((line) => {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  });
  if (dataLines.length === 0) return null;
  return { event, data: JSON.parse(dataLines.join('\n')) };
};
