#include "service_8.h"

Service8::Service8() {}

void Service8::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service8::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
