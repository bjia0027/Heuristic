#include "service_34.h"

Service34::Service34() {}

void Service34::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service34::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
