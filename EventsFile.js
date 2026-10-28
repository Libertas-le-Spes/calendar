.pragma library

var CONTRACT_VERSION = 1
var MAX_EVENT_ROWS = 8000
var MAX_DOCUMENT_BYTES = 16 * 1024 * 1024

function read(raw) {
  if (!raw) return refused("missing")
  if (encodedLength(raw) > MAX_DOCUMENT_BYTES) return refused("too-large")
  var doc = parsed(raw)
  if (!isObject(doc)) return refused("missing")
  if (doc.version !== CONTRACT_VERSION) return refused(versionProblem(doc))
  if (!Array.isArray(doc.events)) return refused("missing")
  if (doc.events.length > MAX_EVENT_ROWS) return refused("too-large")
  return { doc: doc, problem: "" }
}

function eventsOf(result) {
  if (!result.doc) return []
  return result.doc.events
}

function encodedLength(raw) {
  if (raw.length > MAX_DOCUMENT_BYTES) return raw.length
  var bytes = 0
  for (var i = 0; i < raw.length; i++) bytes += unitBytes(raw.charCodeAt(i))
  return bytes
}

function unitBytes(code) {
  if (code < 0x80) return 1
  if (code < 0x800) return 2
  if (code >= 0xd800 && code <= 0xdfff) return 2
  return 3
}

function refused(problem) {
  return { doc: null, problem: problem }
}

function parsed(raw) {
  try {
    return JSON.parse(raw)
  } catch (error) {
    return null
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function versionProblem(doc) {
  if (doc.version === undefined) return "missing"
  return "version"
}
