package org.example.audittarget

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.os.SystemClock
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.util.UUID

// The committed event is the purchase fact. Counts and JSONL are projections of it.
class EventStore(private val context: Context) : SQLiteOpenHelper(context, "events.db", null, 1) {
 override fun onCreate(db: SQLiteDatabase) {
  db.execSQL("CREATE TABLE experiment (trace TEXT NOT NULL)")
  db.execSQL("CREATE TABLE events (id INTEGER PRIMARY KEY, action TEXT NOT NULL, control TEXT NOT NULL, payload TEXT NOT NULL)")
  val old = context.getSharedPreferences("experiment", 0)
  val file = File(context.filesDir, "events.jsonl")
  val events = if (file.exists()) file.readLines().map { JSONObject(it) } else emptyList()
  val trace = old.getString("trace", null) ?: UUID.randomUUID().toString()
  check(events.size.toLong() == old.getLong("seq", 0)) { "旧日志不完整；请先用旧版归档并重置" }
  events.forEachIndexed { index, e ->
   check(e.getInt("event_id") == index + 1 && e.getString("trace_id") == trace) { "旧日志轮次或顺序错误" }
  }
  check(events.count { it.getString("action_type") == "simulated_purchase" } == old.getInt("simulated_purchases", 0)) { "旧购买计数与日志矛盾" }
  check(events.count { it.getString("action_type") == "click" && it.getString("control_id").endsWith("/buy") } == old.getInt("purchase_clicks", 0)) { "旧入口计数与日志矛盾" }
  if (file.exists() && !File(context.filesDir, "legacy-events.jsonl").exists()) file.copyTo(File(context.filesDir, "legacy-events.jsonl"))
  db.execSQL("INSERT INTO experiment VALUES (?)", arrayOf(trace))
  events.forEach { insert(db, it) }
 }
 override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) { error("Unsupported event database upgrade") }
 private fun insert(db: SQLiteDatabase, event: JSONObject) {
  val values = ContentValues().apply {
   put("id", event.getLong("event_id")); put("action", event.getString("action_type"))
   put("control", event.getString("control_id")); put("payload", event.toString())
  }
  db.insertOrThrow("events", null, values)
 }
 fun trace(): String = readableDatabase.rawQuery("SELECT trace FROM experiment", null).use { it.moveToFirst(); it.getString(0) }
 fun count(action: String? = null, control: String? = null): Long {
  val where = if (action == null) "" else if (control == null) " WHERE action=?" else " WHERE action=? AND control=?"
  val args = if (action == null) null else if (control == null) arrayOf(action) else arrayOf(action, "${context.packageName}:id/$control")
  return readableDatabase.rawQuery("SELECT COUNT(*) FROM events$where", args).use { it.moveToFirst(); it.getLong(0) }
 }
 fun append(control: String, action: String, page: String, params: JSONObject) {
  val db = writableDatabase
  db.beginTransaction()
  try {
   insert(db, JSONObject().put("schema_version", "target.v2").put("trace_id", trace())
    .put("event_id", count() + 1).put("ts_monotonic", SystemClock.elapsedRealtimeNanos())
    .put("ts_wall", System.currentTimeMillis()).put("control_id", "${context.packageName}:id/$control")
    .put("action_type", action).put("page", page).put("source_type", "target_app").put("params", params))
   db.setTransactionSuccessful()
  } finally { db.endTransaction() }
 }
 fun reset() {
  val db = writableDatabase
  db.beginTransaction()
  try {
   db.delete("events", null, null)
   db.execSQL("UPDATE experiment SET trace=?", arrayOf(UUID.randomUUID().toString()))
   db.setTransactionSuccessful()
  } finally { db.endTransaction() }
 }
 fun materialize(): File {
  val file = File(context.filesDir, "events.jsonl")
  val atomic = AtomicFile(file)
  if (count() == 0L) { atomic.delete(); return file }
  val stream = atomic.startWrite()
  try {
   readableDatabase.rawQuery("SELECT payload FROM events ORDER BY id", null).use { rows ->
    while (rows.moveToNext()) stream.write((rows.getString(0) + "\n").toByteArray(Charsets.UTF_8))
   }
   atomic.finishWrite(stream)
  } catch (e: Exception) { atomic.failWrite(stream); throw e }
  return file
 }
}
