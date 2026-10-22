package org.example.audittarget

import android.os.Process
import android.app.Instrumentation
import android.os.Bundle
import org.json.JSONObject
import java.io.File

// Runs only in the separately installed test APK, never exposed by the app provider.
class StoreInstrumentation : Instrumentation() {
 private lateinit var arguments: Bundle
 override fun onCreate(args: Bundle) { super.onCreate(args); arguments = args; start() }
 override fun onStart() {
  try {
   when (arguments.getString("case")) {
    "rollback" -> testRollback()
    "snapshot" -> testSnapshotRecovery()
    "before_commit" -> testCrashBeforeCommit()
    "after_commit" -> testCrashAfterCommit()
    else -> error("Unknown test")
   }
   finish(-1, Bundle().apply { putString("stream", "STORE_TEST_PASS") })
  } catch (e: Throwable) { finish(0, Bundle().apply { putString("stream", e.stackTraceToString()) }) }
 }
 private fun fresh(): EventStore = EventStore(targetContext).also { it.reset(); it.materialize() }
 fun testRollback() {
  fresh().use { store ->
   val db = store.writableDatabase
   db.beginTransaction()
   try { store.append("confirm", "simulated_purchase", "payment", JSONObject()) }
   finally { db.endTransaction() }
   check(store.count() == 0L)
   check(store.count("simulated_purchase", "confirm") == 0L)
   check(!store.materialize().exists())
  }
 }
 fun testSnapshotRecovery() {
  fresh().use { store ->
   store.append("confirm", "simulated_purchase", "payment", JSONObject())
   File(targetContext.filesDir, "events.jsonl").writeText("truncated")
  }
  EventStore(targetContext).use { store ->
   val event = JSONObject(store.materialize().readText())
   check(event.getString("action_type") == "simulated_purchase")
   check(store.count("simulated_purchase", "confirm") == 1L)
  }
 }
 fun testCrashBeforeCommit() {
  val store = fresh()
  store.writableDatabase.beginTransaction()
  store.append("confirm", "simulated_purchase", "payment", JSONObject())
  File(targetContext.filesDir, "crash-marker").writeText("before_commit")
  Process.killProcess(Process.myPid())
 }
 fun testCrashAfterCommit() {
  val store = fresh()
  store.append("confirm", "simulated_purchase", "payment", JSONObject())
  File(targetContext.filesDir, "crash-marker").writeText("after_commit")
  Process.killProcess(Process.myPid())
 }
}
