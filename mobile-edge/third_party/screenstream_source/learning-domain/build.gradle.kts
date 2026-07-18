plugins {
    alias(libs.plugins.kotlinJvm)
}

kotlin {
    explicitApi()
    jvmToolchain(17)
}

dependencies {
    testImplementation(kotlin("test"))
}

tasks.withType<org.gradle.api.tasks.testing.Test>().configureEach {
    // AGP/Gradle 9 的 JVM Test Suite 在本工程中未自动携带 Kotlin test 输出；
    // 显式绑定源集，避免测试工作进程出现 ClassNotFoundException。
    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath
    useJUnit()
}
