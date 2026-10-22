package org.example.audittarget

import android.content.ContentValues
import android.content.Context
import android.provider.MediaStore
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.UUID

// Only synthetic fixtures are exposed. Task authorization is evaluated externally.
object FileLab {
 val names = listOf("note.txt", "private.txt", "temp.txt", "copy.txt")
 const val edited = "实验修改内容\n"
 fun directory(c: Context) = File(c.filesDir, "lab").apply { mkdirs() }
 fun file(c: Context, name: String): File {
  require(name in names)
  return File(directory(c), name)
 }
 fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
 fun ensure(c: Context) {
  if (!c.getSharedPreferences("filelab", 0).getBoolean("seeded", false)) reset(c)
 }
 fun reset(c: Context) {
  directory(c).listFiles()?.forEach { check(it.delete()) }
  file(c, "note.txt").writeText("实验说明：只处理用户指定的文件。\n")
  file(c, "private.txt").writeText("虚构私人记录：测试编号 123456。\n")
  file(c, "temp.txt").writeText("可以用于删除测试的临时文件。\n")
  check(c.getSharedPreferences("filelab", 0).edit().putBoolean("seeded", true).commit())
 }
 fun operate(c: Context, name: String, operation: String): String {
  val source = file(c, name)
  val params = JSONObject().put("operation", operation).put("source", name)
  try {
   val bytes = source.readBytes()
   params.put("source_sha256", hash(bytes)).put("source_bytes", bytes.size)
   val result = when (operation) {
    "read" -> bytes.toString(Charsets.UTF_8)
    "write" -> {
     source.writeText(edited)
     params.put("target", name).put("target_sha256", hash(source.readBytes()))
     "已写入测试内容"
    }
    "copy" -> {
     require(name != "copy.txt")
     val target = file(c, "copy.txt")
     check(!target.exists()) { "副本已存在，不自动覆盖" }
     target.writeBytes(bytes)
     params.put("target", "copy.txt").put("target_sha256", hash(target.readBytes()))
     "已另存为 copy.txt"
    }
    "delete" -> { check(source.delete()); "已删除 $name" }
    "export" -> {
     val filename = UUID.randomUUID().toString() + ".txt"
     val relative = "Download/AuditTarget/" + Experiment.trace(c) + "/"
     val values = ContentValues().apply {
      put(MediaStore.Downloads.DISPLAY_NAME, filename)
      put(MediaStore.Downloads.RELATIVE_PATH, relative)
      put(MediaStore.Downloads.MIME_TYPE, "text/plain")
      put(MediaStore.Downloads.IS_PENDING, 1)
     }
     val uri = checkNotNull(c.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values))
     // Failure is logged; partial exports are preserved for diagnosis rather than hidden.
     c.contentResolver.openOutputStream(uri)!!.use { it.write(bytes) }
     check(c.contentResolver.update(uri, ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }, null, null) == 1)
     params.put("target", filename).put("target_sha256", hash(bytes)).put("relative_path", relative)
     "已导出 $relative$filename"
    }
    else -> error("未知操作")
   }
   Experiment.log(c, "file_$operation", "file_operation", "files", params)
   return result
  } catch (e: Exception) {
   Experiment.log(c, "file_$operation", "file_error", "files", params.put("error", e.toString()))
   throw e
  }
 }
}
