#include "service_2.h"

Service2::Service2() {}

void Service2::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service2::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
