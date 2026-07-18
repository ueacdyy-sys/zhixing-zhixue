plugins {
    alias(libs.plugins.kotlinJvm)
}

kotlin {
    explicitApi()
    jvmToolchain(17)
}

dependencies {
    api(projects.learningDomain)
    api(libs.kotlinx.coroutines.android)
    testImplementation(kotlin("test"))
}
